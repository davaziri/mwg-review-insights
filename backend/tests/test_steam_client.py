import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from app.steam.client import (
    APPDETAILS_URL,
    REVIEWS_URL,
    SteamClient,
    SteamError,
    SteamRequestFailed,
    parse_reviews_response,
)
from tests.fakes import appdetails_data, encode_cursor, make_reviews

APP = 3308200


def collect(client, app_id=APP, cursor="*", sort_filter=1):
    return list(client.iter_review_pages(app_id, cursor, sort_filter=sort_filter))


def test_pages_through_all_reviews_until_an_empty_page(fake_steam, steam_client):
    fake_steam.reviews_by_app[APP] = make_reviews(250)

    pages = collect(steam_client)

    reviews = [r for _, page in pages for r in page.reviews]
    assert len(reviews) == 250
    assert len({r["recommendationid"] for r in reviews}) == 250
    assert pages[-1][1].reviews == []
    # 3 full pages, then an empty page that is re-checked once before being accepted as the end.
    assert [r["cursor"] for r in fake_steam.requests] == [
        "*",
        encode_cursor(100),
        encode_cursor(200),
        encode_cursor(250),
        encode_cursor(250),
    ]
    assert [r["num_per_page"] for r in fake_steam.requests] == [100, 100, 100, 100, 99]


def test_request_uses_input_json_with_numeric_enums(fake_steam, steam_client):
    fake_steam.reviews_by_app[APP] = make_reviews(3)

    collect(steam_client)

    first = fake_steam.requests[0]
    assert first == {
        "appid": APP,
        "cursor": "*",
        "filter": 1,
        "num_per_page": 100,
        "languages": ["all"],
        "purchase_type": 1,
        "review_type": 0,
    }
    query = parse_qs(urlsplit(fake_steam.raw_urls[0]).query)
    assert set(query) == {"input_json"}  # no key configured, so none sent


def test_cursor_is_url_encoded(fake_steam, steam_client):
    fake_steam.reviews_by_app[APP] = make_reviews(150)

    collect(steam_client)

    raw_query = urlsplit(fake_steam.raw_urls[1]).query
    assert "+" not in raw_query and "%2B" in raw_query
    # And Steam would decode it back to the exact cursor it handed out.
    assert fake_steam.requests[1]["cursor"] == encode_cursor(100)


def test_publisher_key_is_sent_when_configured(fake_steam, sleeps):
    fake_steam.reviews_by_app[APP] = []
    with SteamClient(publisher_key="SECRET", min_interval=0, sleep=sleeps.append) as client:
        collect(client)
    assert parse_qs(urlsplit(fake_steam.raw_urls[0]).query)["key"] == ["SECRET"]


def test_stops_on_repeated_cursor(sleeps):
    page = {"response": {"reviews": make_reviews(2), "cursor": "same+cursor"}}
    with respx.mock() as mock:
        route = mock.get(REVIEWS_URL).mock(return_value=httpx.Response(200, json=page))
        with SteamClient(min_interval=0, sleep=sleeps.append) as client:
            pages = collect(client)
    assert len(pages) == 2  # "*" then "same+cursor"; the repeat is not followed
    assert route.call_count == 2


def test_stale_empty_page_is_rechecked_with_a_different_page_size(sleeps):
    reviews = make_reviews(3)
    responses = [
        httpx.Response(200, json={"response": {"reviews": reviews[:2], "cursor": "c1"}}),
        httpx.Response(200, json={"response": {"reviews": [], "cursor": "c1"}}),  # stale cache
        httpx.Response(200, json={"response": {"reviews": reviews[2:], "cursor": "c2"}}),
        httpx.Response(200, json={"response": {"reviews": [], "cursor": "c2"}}),
        httpx.Response(200, json={"response": {"reviews": [], "cursor": "c2"}}),
    ]
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(side_effect=responses)
        with SteamClient(min_interval=0, sleep=sleeps.append) as client:
            pages = collect(client)
    assert sum(len(p.reviews) for _, p in pages) == 3


def test_backs_off_exponentially_on_429(sleeps):
    ok = httpx.Response(200, json={"response": {"reviews": []}})
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(side_effect=[httpx.Response(429), httpx.Response(429), httpx.Response(429), ok])
        with SteamClient(min_interval=0, max_retries=5, backoff_base=2, sleep=sleeps.append, jitter=lambda: 0) as client:
            page = client.get_reviews_page(APP, sort_filter=1)
    assert page.reviews == []
    assert sleeps == [2, 4, 8]


def test_honors_retry_after_header(sleeps):
    ok = httpx.Response(200, json={"response": {}})
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), ok])
        with SteamClient(min_interval=0, sleep=sleeps.append, jitter=lambda: 0) as client:
            client.get_reviews_page(APP, sort_filter=1)
    assert sleeps == [7.0]


def test_backoff_is_capped(sleeps):
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(return_value=httpx.Response(503))
        with SteamClient(
            min_interval=0, max_retries=6, backoff_base=2, backoff_max=20, sleep=sleeps.append, jitter=lambda: 0
        ) as client:
            with pytest.raises(SteamRequestFailed, match="7 attempts"):
                client.get_reviews_page(APP, sort_filter=1)
    assert sleeps == [2, 4, 8, 16, 20, 20]


def test_retries_network_errors(sleeps):
    ok = httpx.Response(200, json={"response": {}})
    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(side_effect=[httpx.ConnectError("boom"), ok])
        with SteamClient(min_interval=0, sleep=sleeps.append, jitter=lambda: 0) as client:
            client.get_reviews_page(APP, sort_filter=1)
    assert sleeps == [2]


def test_other_client_errors_are_not_retried(sleeps):
    with respx.mock() as mock:
        route = mock.get(REVIEWS_URL).mock(return_value=httpx.Response(403))
        with SteamClient(min_interval=0, sleep=sleeps.append) as client:
            with pytest.raises(SteamRequestFailed) as exc:
                client.get_reviews_page(APP, sort_filter=1)
    assert exc.value.status_code == 403
    assert route.call_count == 1 and sleeps == []


def test_throttles_to_minimum_interval():
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(round(seconds, 3))
        now[0] += seconds

    with respx.mock() as mock:
        mock.get(REVIEWS_URL).mock(return_value=httpx.Response(200, json={"response": {}}))
        with SteamClient(min_interval=1.0, sleep=sleep, clock=lambda: now[0]) as client:
            client.get_reviews_page(APP, sort_filter=1)
            now[0] += 0.25
            client.get_reviews_page(APP, sort_filter=1)
            now[0] += 3.0
            client.get_reviews_page(APP, sort_filter=1)
    assert sleeps == [0.75]


@pytest.mark.parametrize(
    ("body", "count"),
    [
        ({"response": {}}, 0),  # app Steam doesn't know
        ({"response": {"success": 1, "reviews": make_reviews(2), "cursor": "x"}}, 2),
        ({"success": 1, "reviews": make_reviews(1)}, 1),  # unwrapped shape
    ],
)
def test_parse_response_shapes(body, count):
    assert len(parse_reviews_response(body).reviews) == count


def test_parse_response_rejects_failure():
    with pytest.raises(SteamError):
        parse_reviews_response({"response": {"success": 2}})


def test_appdetails(fake_steam, steam_client):
    fake_steam.appdetails[APP] = appdetails_data("Tombwater", APP)
    assert steam_client.get_appdetails(APP)["name"] == "Tombwater"
    assert steam_client.get_appdetails(999) is None


def test_appdetails_null_body(sleeps):
    with respx.mock() as mock:
        mock.get(APPDETAILS_URL).mock(return_value=httpx.Response(200, content=json.dumps(None)))
        with SteamClient(min_interval=0, sleep=sleeps.append) as client:
            assert client.get_appdetails(APP) is None
