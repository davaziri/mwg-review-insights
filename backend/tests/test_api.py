from app.steam.sync import run_sync
from tests.fakes import appdetails_data, make_reviews


def test_lists_seed_titles_with_no_reviews(api, fake_steam):
    titles = api.get("/api/titles").json()
    assert len(titles) == 8
    tomb = titles[0]
    assert tomb["name"] == "Tombwater" and tomb["steam_app_id"] == 3308200
    assert tomb["apps"][0]["stored_reviews"] == 0 and tomb["last_synced_at"] is None
    godstv = next(t for t in titles if t["name"] == "GodsTV")
    assert [a["is_demo"] for a in godstv["apps"]] == [False, True]


def test_sync_now_queues_a_run_and_stats_follow(api, fake_steam, session_factory, settings, steam_client):
    fake_steam.reviews_by_app[3308200] = make_reviews(12)

    runs = api.post("/api/titles/1/sync").json()
    assert [(r["status"], r["mode"]) for r in runs] == [("queued", "full")]
    assert api.get("/api/titles/1").json()["apps"][0]["active_run"]["status"] == "queued"

    from app.models import SyncRun

    with session_factory() as s:
        run_sync(s, settings, steam_client, s.get(SyncRun, runs[0]["id"]))

    title = api.get("/api/titles/1").json()
    app_stats = title["apps"][0]
    assert app_stats["stored_reviews"] == 12 and app_stats["stored_positive"] == 12
    assert app_stats["latest_snapshot"]["total_reviews"] == 12
    assert app_stats["last_run"]["status"] == "succeeded" and app_stats["active_run"] is None
    assert title["last_synced_at"] is not None
    log = api.get("/api/sync-runs").json()
    assert log[0]["title_name"] == "Tombwater"


def test_add_title_fetches_store_details_and_queues_sync(api, fake_steam):
    fake_steam.appdetails[999001] = appdetails_data("New Signing", 999001, coming_soon=True, date="Coming soon")

    resp = api.post("/api/titles", json={"steam_app_id": 999001, "status": "unreleased"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Signing" and body["coming_soon"] is True
    assert body["release_date"] is None and body["release_date_text"] == "Coming soon"
    assert body["apps"][0]["active_run"]["status"] == "queued"
    assert api.post("/api/titles", json={"steam_app_id": 999001}).status_code == 409


def test_add_title_still_saves_when_steam_has_no_page(api, fake_steam):
    body = api.post("/api/titles", json={"steam_app_id": 999002, "sync_now": False}).json()
    assert body["name"] == "Steam app 999002"


def test_archive_hides_title_and_blocks_sync(api, fake_steam):
    assert api.post("/api/titles/2/archive").json()["archived_at"] is not None
    names = [t["name"] for t in api.get("/api/titles").json()]
    assert "Duck Paradox" not in names
    assert "Duck Paradox" in [t["name"] for t in api.get("/api/titles?include_archived=true").json()]
    assert api.post("/api/titles/2/sync").status_code == 409

    api.post("/api/titles/2/unarchive")
    assert "Duck Paradox" in [t["name"] for t in api.get("/api/titles").json()]


def test_edit_and_delete_title(api, fake_steam):
    assert api.patch("/api/titles/3", json={"status": "early_access", "notes": "x"}).json()["status"] == "early_access"
    assert api.patch("/api/titles/3", json={"status": "bogus"}).status_code == 422

    api.post("/api/titles/3/sync")
    assert api.delete("/api/titles/3").status_code == 409  # sync pending

    assert api.delete("/api/titles/4").status_code == 204
    assert api.get("/api/titles/4").status_code == 404


def test_sync_all_queues_every_active_title(api, fake_steam):
    runs = api.post("/api/sync/all").json()
    # 8 titles, GodsTV has a demo app too
    assert len(runs) == 9
