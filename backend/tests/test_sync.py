from datetime import timedelta

from sqlalchemy import func, select

from app.models import Review, ReviewSnapshot, SyncRun, Title
from app.steam.client import SteamClient
from app.steam.sync import choose_mode, enqueue_sync, run_sync
from app.timeutil import utcnow
from app.worker.runner import enqueue_all_active, process_queue, recover_interrupted
from tests.fakes import encode_cursor, make_review, make_reviews

APP = 3308200


def sync(session, settings, client, title, mode=None) -> list[SyncRun]:
    runs = enqueue_sync(session, settings, title, trigger="manual", mode=mode)
    return [run_sync(session, settings, client, run) for run in runs]


def active_count(session, app_id=APP) -> int:
    return session.scalar(
        select(func.count()).select_from(Review).where(Review.app_id == app_id, Review.deleted_at.is_(None))
    )


def test_full_sync_stores_every_review_and_a_snapshot(session, settings, steam_client, fake_steam, title):
    fake_steam.reviews_by_app[APP] = make_reviews(250)

    (run,) = sync(session, settings, steam_client, title)

    assert run.status == "succeeded" and run.mode == "full"
    assert run.new_count == 250 and run.reviews_seen == 250
    assert active_count(session) == 250
    snap = session.scalar(select(ReviewSnapshot))
    assert (snap.total_reviews, snap.review_score_desc) == (250, "Very Positive")
    assert run.steam_total == 250


def test_review_fields_are_mapped_and_raw_json_kept(session, settings, steam_client, fake_steam, title):
    raw = make_review(
        42,
        created=1_750_000_000,
        voted_up=False,
        language="schinese",
        text="太难了",
        developer_response="Thanks, patch incoming",
        timestamp_dev_responded=1_750_100_000,
        primarily_steam_deck=True,
        refunded=True,
    )
    fake_steam.reviews_by_app[APP] = [raw]

    sync(session, settings, steam_client, title)

    r = session.scalar(select(Review))
    assert r.recommendation_id == "42" and r.title_id == title.id and r.app_id == APP
    assert (r.language, r.review_text, r.voted_up) == ("schinese", "太难了", False)
    assert r.weighted_vote_score == 0.523809552192687988  # Steam sends a string
    assert (r.primarily_steam_deck, r.refunded, r.steam_purchase) == (True, True, True)
    assert r.developer_response == "Thanks, patch incoming" and r.timestamp_dev_responded == 1_750_100_000
    assert (r.author_playtime_at_review, r.author_playtime_forever, r.author_num_reviews) == (600, 900, 4)
    assert r.raw_json == raw


def test_second_sync_only_fetches_new_and_edited_reviews(session, settings, steam_client, fake_steam, title):
    reviews = make_reviews(250)
    fake_steam.reviews_by_app[APP] = reviews
    sync(session, settings, steam_client, title)
    first_sync_requests = len(fake_steam.requests)

    newest = reviews[-1]["timestamp_created"]
    reviews.append(make_review(9001, newest + 100))
    reviews.append(make_review(9002, newest + 200))
    reviews[10] = make_review(1010, reviews[10]["timestamp_created"], updated=newest + 300, text="Edited: now 9/10")

    (run,) = sync(session, settings, steam_client, title)

    assert run.mode == "incremental"
    assert (run.new_count, run.updated_count, run.deleted_count) == (2, 1, 0)
    assert run.pages_fetched == 1
    second = fake_steam.requests[first_sync_requests:]
    assert len(second) == 1 and second[0]["filter"] == settings.steam_filter_incremental
    assert session.scalar(select(Review).where(Review.recommendation_id == "1010")).review_text == "Edited: now 9/10"
    assert active_count(session) == 252


def test_vote_count_changes_alone_do_not_count_as_edits(session, settings, steam_client, fake_steam, title):
    reviews = make_reviews(5)
    fake_steam.reviews_by_app[APP] = reviews
    sync(session, settings, steam_client, title)
    for r in reviews:
        r["votes_up"] = 99

    (run,) = sync(session, settings, steam_client, title, mode="full")

    assert run.updated_count == 0
    assert session.scalar(select(func.min(Review.votes_up))) == 99


def test_full_sync_marks_missing_reviews_deleted_and_restores_returning_ones(
    session, settings, steam_client, fake_steam, title
):
    reviews = make_reviews(40)
    fake_steam.reviews_by_app[APP] = list(reviews)
    sync(session, settings, steam_client, title)

    fake_steam.reviews_by_app[APP] = reviews[2:]
    (run,) = sync(session, settings, steam_client, title, mode="full")
    assert run.deleted_count == 2
    assert active_count(session) == 38
    gone = session.scalar(select(Review).where(Review.recommendation_id == reviews[0]["recommendationid"]))
    assert gone.deleted_at is not None  # kept, not hard-deleted

    fake_steam.reviews_by_app[APP] = reviews[1:]
    (run,) = sync(session, settings, steam_client, title, mode="full")
    assert (run.restored_count, run.deleted_count) == (1, 0)
    assert active_count(session) == 39


def test_incremental_sync_never_marks_deletions(session, settings, steam_client, fake_steam, title):
    reviews = make_reviews(10)
    fake_steam.reviews_by_app[APP] = reviews
    sync(session, settings, steam_client, title)
    fake_steam.reviews_by_app[APP] = reviews[5:]

    (run,) = sync(session, settings, steam_client, title, mode="incremental")

    assert run.deleted_count == 0 and active_count(session) == 10


def test_mass_disappearance_is_not_marked_deleted(session, settings, steam_client, fake_steam, title):
    reviews = make_reviews(100)
    fake_steam.reviews_by_app[APP] = reviews
    sync(session, settings, steam_client, title)
    fake_steam.reviews_by_app[APP] = reviews[:40]

    (run,) = sync(session, settings, steam_client, title, mode="full")

    assert run.status == "succeeded" and run.deleted_count == 0
    assert "Did not mark 60 of 100" in run.warning
    assert active_count(session) == 100


def test_failed_run_resumes_from_its_saved_cursor(session, settings, steam_client, fake_steam, title):
    fake_steam.reviews_by_app[APP] = make_reviews(250)
    fake_steam.fail_offsets = {200}  # page 3 keeps returning HTTP 500

    (failed,) = sync(session, settings, steam_client, title)
    assert failed.status == "failed" and "Gave up" in failed.error
    assert failed.pages_fetched == 2 and failed.cursor == encode_cursor(200)
    assert active_count(session) == 200

    fake_steam.fail_offsets = set()
    seen_before = len(fake_steam.requests)
    (resumed,) = sync(session, settings, steam_client, title)

    assert resumed.status == "succeeded" and resumed.resumed_from_id == failed.id
    assert resumed.mode == "full" and resumed.crawl_started_at == failed.crawl_started_at
    assert fake_steam.requests[seen_before]["cursor"] == encode_cursor(200)  # not "*"
    assert active_count(session) == 250
    assert resumed.deleted_count == 0  # reviews from the first attempt still count as seen


def test_worker_requeues_runs_left_running(session, session_factory, settings, steam_client, fake_steam, title):
    fake_steam.reviews_by_app[APP] = make_reviews(150)
    (run,) = enqueue_sync(session, settings, title, trigger="schedule")
    run.status, run.cursor, run.crawl_started_at = "running", encode_cursor(100), utcnow()
    session.commit()

    assert recover_interrupted(session) == 1
    assert process_queue(session_factory, settings, steam_client) == 1

    session.refresh(run)
    assert run.status == "succeeded"
    assert fake_steam.requests[0]["cursor"] == encode_cursor(100)
    assert active_count(session) == 50


def test_enqueue_does_not_duplicate_a_pending_run(session, settings, title):
    first = enqueue_sync(session, settings, title, trigger="manual")
    second = enqueue_sync(session, settings, title, trigger="manual")
    assert [r.id for r in first] == [r.id for r in second]
    assert session.scalar(select(func.count()).select_from(SyncRun)) == 1


def test_demo_app_is_synced_separately(session, settings, steam_client, fake_steam):
    title = Title(name="GodsTV", steam_app_id=2626570, demo_app_id=3673170, status="coming_soon")
    session.add(title)
    session.commit()
    fake_steam.reviews_by_app[3673170] = make_reviews(3, start_id=5000)

    runs = sync(session, settings, steam_client, title)

    assert [r.app_id for r in runs] == [2626570, 3673170]
    assert all(r.status == "succeeded" for r in runs)
    assert active_count(session, 2626570) == 0
    assert active_count(session, 3673170) == 3


def test_title_with_no_reviews_syncs_cleanly(session, settings, steam_client, fake_steam):
    title = Title(name="The Legend of Baboo", steam_app_id=2928040, status="unreleased")
    session.add(title)
    session.commit()

    (run,) = sync(session, settings, steam_client, title)

    assert run.status == "succeeded" and run.new_count == 0
    assert session.scalar(select(ReviewSnapshot)).total_reviews == 0

    # Once reviews exist, the next nightly sync picks them up with no changes needed.
    fake_steam.reviews_by_app[2928040] = make_reviews(4)
    (run,) = sync(session, settings, steam_client, title)
    assert run.mode == "incremental" and run.new_count == 4


def test_choose_mode(session, settings, steam_client, fake_steam, title):
    assert choose_mode(session, settings, title.id, APP) == "full"

    fake_steam.reviews_by_app[APP] = make_reviews(20)
    (run,) = sync(session, settings, steam_client, title)
    assert choose_mode(session, settings, title.id, APP) == "incremental"

    # Steam now reports far more reviews than we hold; the last full crawl is over a day old.
    session.scalar(select(ReviewSnapshot)).total_reviews = 40
    run.finished_at = utcnow() - timedelta(days=2)
    session.commit()
    assert choose_mode(session, settings, title.id, APP) == "full"

    # A full crawl is also forced once the weekly interval passes.
    session.scalar(select(ReviewSnapshot)).total_reviews = 20
    run.finished_at = utcnow() - timedelta(days=settings.full_sync_interval_days + 1)
    session.commit()
    assert choose_mode(session, settings, title.id, APP) == "full"


def test_sync_refreshes_stale_appdetails(session, settings, steam_client, fake_steam, title):
    from tests.fakes import appdetails_data

    fake_steam.appdetails[APP] = appdetails_data("Tombwater", APP, date="2 Jun, 2025")
    sync(session, settings, steam_client, title)

    session.refresh(title)
    assert title.header_image_url.endswith(f"/{APP}/header.jpg")
    assert title.release_date.isoformat() == "2025-06-02"
    assert title.developers == ["Example Dev"]


def test_nightly_enqueues_only_active_titles(session, settings, title):
    archived = Title(name="Old", steam_app_id=1, status="released", archived_at=utcnow())
    session.add(archived)
    session.commit()

    runs = enqueue_all_active(session, settings)

    assert [r.title_id for r in runs] == [title.id]
    assert runs[0].trigger == "schedule"


def test_client_from_settings_uses_faster_interval_with_key(settings):
    settings.steam_publisher_key = "k"
    client = SteamClient.from_settings(settings)
    assert client._min_interval == settings.steam_request_interval_with_key_seconds
    client.close()
