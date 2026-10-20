"""End to end against real Steam responses for Tombwater, recorded with
`python -m app.cli record-fixtures` (author Steam IDs replaced). No live calls.

Flow: "Sync now" through the API, the worker drains the queue (full crawl), the Titles API
reports stored counts equal to Steam's totals, then a second sync runs incrementally and
stops after one page.
"""

import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from app.steam.client import APPDETAILS_URL, REVIEWS_URL, SteamClient
from app.worker.runner import process_queue

RECORDED = Path(__file__).parent / "fixtures" / "steam" / "recorded"
APP = 3308200


class RecordedSteam:
    def __init__(self, app_id: int):
        self.pages: dict[tuple[int, str], dict] = {}
        for path in RECORDED.glob(f"reviews_{app_id}_filter*_page*.json"):
            sort_filter = int(re.search(r"filter(\d+)", path.name).group(1))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.pages[(sort_filter, data["request_cursor"])] = data["body"]
        self.appdetails = json.loads((RECORDED / f"appdetails_{app_id}.json").read_text(encoding="utf-8"))
        self.requests: list[dict] = []

    def reviews(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.url.params["input_json"])
        self.requests.append(body)
        page = self.pages.get((body["filter"], body["cursor"]))
        if page is None:
            return httpx.Response(404, json={"error": f"no recording for {body['filter']}/{body['cursor']}"})
        return httpx.Response(200, json=page)

    def details(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={str(APP): {"success": True, "data": self.appdetails}})

    def totals(self) -> dict:
        return self.pages[(1, "*")]["response"]["query_summary"]


@pytest.fixture
def recorded():
    if not any(RECORDED.glob(f"reviews_{APP}_filter1_page*.json")):
        pytest.skip("no recorded Steam responses")
    steam = RecordedSteam(APP)
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(side_effect=steam.reviews)
        mock.get(APPDETAILS_URL).mock(side_effect=steam.details)
        yield steam


def test_full_then_incremental_sync_on_recorded_tombwater(api, recorded, session_factory, settings):
    client = SteamClient(min_interval=0, max_retries=0, sleep=lambda s: None)
    totals = recorded.totals()

    # First sync: full crawl of every review.
    (run,) = api.post("/api/titles/1/sync").json()
    assert run["mode"] == "full"
    assert process_queue(session_factory, settings, client) == 1

    title = api.get("/api/titles/1").json()
    stats = title["apps"][0]
    assert stats["last_run"]["status"] == "succeeded", stats["last_run"]["error"]
    assert stats["stored_reviews"] == totals["total_reviews"] == stats["latest_snapshot"]["total_reviews"]
    assert stats["stored_positive"] == totals["total_positive"]
    assert stats["latest_snapshot"]["review_score_desc"] == totals["review_score_desc"]
    assert (title["name"], title["developers"], title["release_date"]) == (
        recorded.appdetails["name"],
        recorded.appdetails["developers"],
        "2026-03-31",
    )
    assert all(r["filter"] == 1 for r in recorded.requests)

    # Second sync: incremental, one page, nothing new or edited.
    before = len(recorded.requests)
    (run,) = api.post("/api/titles/1/sync").json()
    assert run["mode"] == "incremental"
    process_queue(session_factory, settings, client)

    last = api.get("/api/titles/1").json()["apps"][0]["last_run"]
    assert last["status"] == "succeeded", last["error"]
    assert (last["pages_fetched"], last["new_count"], last["updated_count"]) == (1, 0, 0)
    assert [r["filter"] for r in recorded.requests[before:]] == [settings.steam_filter_incremental]
