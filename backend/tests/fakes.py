"""An in-memory stand-in for Steam's GetAppReviews and appdetails endpoints, for tests."""

import json
import re

import httpx

CURSOR_RE = re.compile(r"^AoJ\+(\d+)/x=$")


def encode_cursor(offset: int) -> str:
    # Real Steam cursors are base64-like and contain '+', '/' and '='; so do these.
    return f"AoJ+{offset}/x="


def decode_cursor(cursor: str) -> int:
    if cursor == "*":
        return 0
    match = CURSOR_RE.match(cursor)
    if not match:
        raise ValueError(f"bad cursor {cursor!r}")
    return int(match.group(1))


def make_review(
    rec_id: int,
    created: int,
    updated: int | None = None,
    *,
    voted_up: bool = True,
    text: str = "Fun game, tight controls.",
    language: str = "english",
    **extra,
) -> dict:
    review = {
        "recommendationid": str(rec_id),
        "author": {
            "steamid": f"7656119800{rec_id:07d}",
            "num_games_owned": 120,
            "num_reviews": 4,
            "playtime_forever": 900,
            "playtime_last_two_weeks": 30,
            "playtime_at_review": 600,
            "deck_playtime_at_review": 0,
            "last_played": created + 1000,
        },
        "language": language,
        "review": text,
        "timestamp_created": created,
        "timestamp_updated": updated if updated is not None else created,
        "voted_up": voted_up,
        "votes_up": 3,
        "votes_funny": 0,
        "weighted_vote_score": "0.523809552192687988",
        "comment_count": 0,
        "steam_purchase": True,
        "received_for_free": False,
        "refunded": False,
        "written_during_early_access": False,
        "primarily_steam_deck": False,
    }
    review.update(extra)
    return review


def make_reviews(count: int, start_id: int = 1000, start_ts: int = 1_750_000_000, step: int = 3600) -> list[dict]:
    """count reviews, one per `step` seconds, oldest first."""
    return [make_review(start_id + i, start_ts + i * step) for i in range(count)]


class FakeSteam:
    """Serves reviews per app id, sorted the way Steam sorts for the requested filter."""

    def __init__(self, reviews_by_app: dict[int, list[dict]] | None = None):
        self.reviews_by_app = reviews_by_app or {}
        self.requests: list[dict] = []
        self.raw_urls: list[str] = []
        self.fail_offsets: set[int] = set()
        self.appdetails: dict[int, dict | None] = {}

    def reviews_handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.url.params["input_json"])
        self.requests.append(body)
        self.raw_urls.append(str(request.url))
        offset = decode_cursor(body["cursor"])
        if offset in self.fail_offsets:
            return httpx.Response(500)

        reviews = list(self.reviews_by_app.get(body["appid"], []))
        key = "timestamp_created" if body["filter"] == 1 else "timestamp_updated"
        reviews.sort(key=lambda r: (r[key], r["recommendationid"]), reverse=True)
        page = reviews[offset : offset + body["num_per_page"]]
        positive = sum(1 for r in reviews if r["voted_up"])
        return httpx.Response(
            200,
            json={
                "response": {
                    "success": 1,
                    "query_summary": {
                        "num_reviews": len(page),
                        "review_score": 8,
                        "review_score_desc": "Very Positive",
                        "total_positive": positive,
                        "total_negative": len(reviews) - positive,
                        "total_reviews": len(reviews),
                    },
                    "reviews": page,
                    "cursor": encode_cursor(offset + len(page)) if page else body["cursor"],
                }
            },
        )

    def appdetails_handler(self, request: httpx.Request) -> httpx.Response:
        app_id = int(request.url.params["appids"])
        data = self.appdetails.get(app_id)
        if data is None:
            return httpx.Response(200, json={str(app_id): {"success": False}})
        return httpx.Response(200, json={str(app_id): {"success": True, "data": data}})

    def requests_for(self, app_id: int) -> list[dict]:
        return [r for r in self.requests if r["appid"] == app_id]


def appdetails_data(name: str, app_id: int, date: str = "Jun 2, 2025", coming_soon: bool = False) -> dict:
    return {
        "type": "game",
        "name": name,
        "steam_appid": app_id,
        "header_image": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg",
        "developers": ["Example Dev"],
        "publishers": ["Midwest Games"],
        "release_date": {"coming_soon": coming_soon, "date": date},
    }
