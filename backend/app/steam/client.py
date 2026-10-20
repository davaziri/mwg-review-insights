"""HTTP client for the Steam endpoints this app uses.

Reviews come from IUserReviewsService/GetAppReviews (documented Steam Web API). Title metadata
comes from the store's appdetails JSON endpoint. No HTML is ever fetched or parsed.
"""

import json
import logging
import random
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

REVIEWS_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

FIRST_CURSOR = "*"
PURCHASE_TYPE_ALL = 1
REVIEW_TYPE_ALL = 0


class SteamError(Exception):
    pass


class SteamRequestFailed(SteamError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ReviewPage:
    reviews: list[dict]
    cursor: str | None
    query_summary: dict | None


def build_reviews_request(app_id: int, cursor: str, sort_filter: int, num_per_page: int) -> dict:
    """The input_json body for GetAppReviews. Enum values must be numbers, not names."""
    return {
        "appid": app_id,
        "cursor": cursor,
        "filter": sort_filter,
        "num_per_page": num_per_page,
        "languages": ["all"],
        "purchase_type": PURCHASE_TYPE_ALL,
        "review_type": REVIEW_TYPE_ALL,
    }


def parse_reviews_response(body: Any) -> ReviewPage:
    if not isinstance(body, dict):
        raise SteamError(f"Unexpected GetAppReviews response: {type(body).__name__}")
    data = body.get("response", body)
    if not isinstance(data, dict):
        raise SteamError("Unexpected GetAppReviews response: 'response' is not an object")
    success = data.get("success")
    if success is not None and success not in (1, True):
        raise SteamError(f"Steam reported success={success!r}")
    return ReviewPage(
        reviews=list(data.get("reviews") or []),
        cursor=data.get("cursor"),
        query_summary=data.get("query_summary"),
    )


class SteamClient:
    """Throttled Steam client with exponential backoff on 429, 5xx and network errors.

    One instance enforces a minimum gap between requests, so share it across a whole sync.
    """

    def __init__(
        self,
        *,
        publisher_key: str | None = None,
        min_interval: float = 1.0,
        max_retries: int = 8,
        backoff_base: float = 2.0,
        backoff_max: float = 300.0,
        timeout: float = 30.0,
        num_per_page: int = 100,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ):
        self._publisher_key = publisher_key
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self.num_per_page = num_per_page
        self._http = http or httpx.Client(
            timeout=timeout, headers={"User-Agent": "mwg-review-insights/0.1"}
        )
        self._owns_http = http is None
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._lock = threading.Lock()
        self._last_request_at: float | None = None

    @classmethod
    def from_settings(cls, settings: Settings, **overrides: Any) -> "SteamClient":
        kwargs: dict[str, Any] = dict(
            publisher_key=settings.steam_publisher_key,
            min_interval=settings.steam_request_interval,
            max_retries=settings.steam_max_retries,
            backoff_base=settings.steam_backoff_base_seconds,
            backoff_max=settings.steam_backoff_max_seconds,
            timeout=settings.steam_timeout_seconds,
            num_per_page=settings.steam_num_per_page,
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "SteamClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Low-level request handling

    def _wait_for_slot(self) -> None:
        with self._lock:
            if self._last_request_at is not None:
                wait = self._min_interval - (self._clock() - self._last_request_at)
                if wait > 0:
                    self._sleep(wait)
            self._last_request_at = self._clock()

    def _backoff_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), self._backoff_max)
            except ValueError:
                pass
        return min(self._backoff_base * (2**attempt), self._backoff_max) + self._jitter()

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        attempt = 0
        while True:
            self._wait_for_slot()
            retry_after = None
            try:
                resp = self._http.get(url, params=params)
            except httpx.TransportError as exc:
                problem = f"network error ({type(exc).__name__})"
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError:
                        problem = "response was not valid JSON"
                elif resp.status_code == 429 or resp.status_code >= 500:
                    problem = f"HTTP {resp.status_code}"
                    retry_after = resp.headers.get("Retry-After")
                else:
                    raise SteamRequestFailed(
                        f"Steam returned HTTP {resp.status_code}", status_code=resp.status_code
                    )

            if attempt >= self._max_retries:
                tries = attempt + 1
                raise SteamRequestFailed(f"Gave up after {tries} attempt{'s' if tries != 1 else ''}: {problem}")
            delay = self._backoff_delay(attempt, retry_after)
            # Never log params: they can contain the publisher key.
            log.warning("Steam request failed (%s); retrying in %.1fs", problem, delay)
            self._sleep(delay)
            attempt += 1

    # Reviews

    def get_reviews_raw(
        self,
        app_id: int,
        cursor: str = FIRST_CURSOR,
        *,
        sort_filter: int,
        num_per_page: int | None = None,
    ) -> Any:
        """The decoded GetAppReviews response body, unparsed."""
        request = build_reviews_request(app_id, cursor, sort_filter, num_per_page or self.num_per_page)
        # httpx percent-encodes the whole value, which covers the cursor's '+', '/' and '='.
        params: dict[str, Any] = {"input_json": json.dumps(request, separators=(",", ":"))}
        if self._publisher_key:
            params["key"] = self._publisher_key
        return self._get_json(REVIEWS_URL, params)

    def get_reviews_page(
        self,
        app_id: int,
        cursor: str = FIRST_CURSOR,
        *,
        sort_filter: int,
        num_per_page: int | None = None,
    ) -> ReviewPage:
        return parse_reviews_response(
            self.get_reviews_raw(app_id, cursor, sort_filter=sort_filter, num_per_page=num_per_page)
        )

    def iter_review_pages(
        self, app_id: int, cursor: str = FIRST_CURSOR, *, sort_filter: int
    ) -> Iterator[tuple[str, ReviewPage]]:
        """Yield (cursor used, page) until Steam returns an empty page.

        The final empty page is yielded too, so callers always see a query_summary even for an
        app with no reviews. Before accepting an empty page as the end, the same cursor is
        requested once more with a different page size, because Steam can serve a stale cached
        response to keyless callers.
        """
        used: set[str] = set()
        while True:
            page = self.get_reviews_page(app_id, cursor, sort_filter=sort_filter)
            if not page.reviews and cursor != FIRST_CURSOR:
                recheck = self.get_reviews_page(
                    app_id, cursor, sort_filter=sort_filter, num_per_page=self.num_per_page - 1
                )
                if recheck.reviews:
                    log.info("Empty page for app %s was stale; continuing", app_id)
                    page = recheck
            yield cursor, page
            if not page.reviews:
                return
            used.add(cursor)
            next_cursor = page.cursor
            if not next_cursor or next_cursor in used:
                log.warning("Steam returned a missing or repeated cursor for app %s; stopping", app_id)
                return
            cursor = next_cursor

    # Store metadata

    def get_appdetails(self, app_id: int) -> dict | None:
        """Store metadata for an app, or None if Steam has no public page for it."""
        body = self._get_json(APPDETAILS_URL, {"appids": app_id, "cc": "us", "l": "english"})
        entry = (body or {}).get(str(app_id)) or {}
        if not entry.get("success"):
            return None
        return entry.get("data")
