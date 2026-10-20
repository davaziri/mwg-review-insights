"""Sign-in with Google (Google's side faked), the admin and viewer rules, and managing people."""

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.auth import GOOGLE_TOKEN_URL, SESSION_COOKIE

ADMIN = "boss@midwestgames.com"
CSRF = {"X-Requested-With": "mwg"}


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


@pytest.fixture
def google(settings):
    settings.auth_mode = "google"
    settings.google_client_id = "client-123"
    settings.google_client_secret = "secret"
    settings.allowed_domains = "midwestgames.com"
    settings.admin_emails = ADMIN
    settings.session_secret = "test-secret"
    return settings


def sign_in(api, email: str, *, hd: str | None = "midwestgames.com", tweak: dict | None = None, next_path: str = "/titles/2"):
    """Go through the whole sign-in on a fresh browser. Returns (client, final response)."""
    client = TestClient(api.app)
    start = client.get("/api/auth/login", params={"next": next_path}, follow_redirects=False)
    assert start.status_code == 302
    query = parse_qs(urlparse(start.headers["location"]).query)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "client-123",
        "exp": time.time() + 600,
        "nonce": query["nonce"][0],
        "email": email,
        "email_verified": True,
        "name": email.split("@")[0].title(),
        **({"hd": hd} if hd else {}),
        **(tweak or {}),
    }
    token = f"{b64({'alg': 'RS256'})}.{b64(claims)}.sig"
    with respx.mock(assert_all_called=False) as mock:
        mock.post(GOOGLE_TOKEN_URL).mock(return_value=httpx.Response(200, json={"id_token": token, "access_token": "x"}))
        done = client.get("/api/auth/callback", params={"code": "abc", "state": query["state"][0]}, follow_redirects=False)
    return client, done


def test_local_mode_is_an_admin_without_signing_in(api):
    me = api.get("/api/auth/me").json()
    assert me["mode"] == "local" and me["user"]["role"] == "admin"
    assert api.get("/api/titles").status_code == 200


def test_google_mode_needs_setup_and_sign_in(api, settings):
    settings.auth_mode = "google"
    me = api.get("/api/auth/me").json()
    assert me["user"] is None and "GOOGLE_CLIENT_ID" in me["problem"] and "ALLOWED_DOMAINS" in me["problem"]
    assert api.get("/api/titles").status_code == 401
    resp = api.get("/api/auth/login", follow_redirects=False)
    assert resp.status_code == 302 and "signin_error=" in resp.headers["location"]
    assert api.get("/api/health").status_code == 200  # always open


def test_sign_in_flow_and_roles(api, google):
    start = TestClient(api.app).get("/api/auth/login", follow_redirects=False)
    url = urlparse(start.headers["location"])
    params = parse_qs(url.query)
    assert url.netloc == "accounts.google.com" and params["hd"] == ["midwestgames.com"]
    assert params["redirect_uri"] == ["http://testserver/api/auth/callback"] and params["scope"] == ["openid email profile"]

    admin, done = sign_in(api, ADMIN)
    assert done.status_code == 302 and done.headers["location"] == "/titles/2"
    assert admin.get("/api/auth/me").json()["user"] == {"id": 1, "email": ADMIN, "name": "Boss", "role": "admin"}
    assert admin.post("/api/titles/1/sync", headers=CSRF).status_code == 200
    assert admin.post("/api/titles/1/sync").status_code == 403  # no header: not from the app
    assert admin.get("/api/sync-runs").json()[0]["requested_by"] == ADMIN

    viewer, _ = sign_in(api, "fan@midwestgames.com")
    assert viewer.get("/api/auth/me").json()["user"]["role"] == "viewer"
    assert viewer.get("/api/titles").status_code == 200
    assert viewer.get("/api/portfolio").status_code == 200
    assert viewer.get("/api/titles/1/export.csv").status_code == 200  # viewers can export
    denied = viewer.post("/api/titles/1/sync", headers=CSRF)
    assert denied.status_code == 403 and "Only admins" in denied.json()["detail"]
    assert viewer.patch("/api/titles/1", json={"name": "x"}, headers=CSRF).status_code == 403
    assert viewer.get("/api/users").status_code == 403

    # Signing out ends the session.
    assert viewer.post("/api/auth/logout").status_code == 204
    assert viewer.get("/api/titles").status_code == 401


@pytest.mark.parametrize(
    ("email", "hd", "tweak", "message"),
    [
        ("someone@gmail.com", None, None, "can't sign in here"),
        ("fan@midwestgames.com", None, None, "work Google account"),  # personal account using a company address
        ("fan@midwestgames.com", "midwestgames.com", {"email_verified": False}, "can't sign in here"),
        ("fan@midwestgames.com", "midwestgames.com", {"aud": "someone-else"}, "wasn't meant for this app"),
        ("fan@midwestgames.com", "midwestgames.com", {"nonce": "replayed"}, "expired"),
    ],
)
def test_sign_in_rejections(api, google, email, hd, tweak, message):
    client, done = sign_in(api, email, hd=hd, tweak=tweak)
    assert done.status_code == 302 and "signin_error=" in done.headers["location"]
    assert message in parse_qs(urlparse(done.headers["location"]).query)["signin_error"][0]
    assert client.get("/api/titles").status_code == 401


def test_forged_or_stale_sessions_are_refused(api, google):
    client, _ = sign_in(api, ADMIN)
    good = client.cookies.get(SESSION_COOKIE)
    payload, mac = good.split(".")
    forged = b64({"uid": 1, "exp": time.time() + 10**6}) + "." + mac
    other = TestClient(api.app)
    other.cookies.set(SESSION_COOKIE, forged)
    assert other.get("/api/titles").status_code == 401
    # A wrong state (another tab, or someone else's link) is refused too.
    stray = TestClient(api.app)
    stray.get("/api/auth/login", follow_redirects=False)
    resp = stray.get("/api/auth/callback", params={"code": "abc", "state": "not-it"}, follow_redirects=False)
    assert "signin_error=" in resp.headers["location"]
    # Only paths inside the app are used after signing in.
    _, done = sign_in(api, ADMIN, next_path="//evil.example.com")
    assert done.headers["location"] == "/"


def test_managing_people(api, google):
    admin, _ = sign_in(api, ADMIN)
    viewer, _ = sign_in(api, "fan@midwestgames.com")
    people = admin.get("/api/users").json()
    assert [(p["email"], p["role"]) for p in people] == [(ADMIN, "admin"), ("fan@midwestgames.com", "viewer")]
    fan_id = people[1]["id"]

    # The last admin can't step down or be turned off.
    assert admin.patch("/api/users/1", json={"role": "viewer"}, headers=CSRF).status_code == 409
    assert admin.patch(f"/api/users/{fan_id}", json={"role": "admin"}, headers=CSRF).json()["role"] == "admin"
    assert viewer.post("/api/titles/1/sync", headers=CSRF).status_code == 200  # now an admin
    # Turning someone off signs them out at once.
    assert admin.patch(f"/api/users/{fan_id}", json={"active": False}, headers=CSRF).json()["active"] is False
    assert viewer.get("/api/titles").status_code == 401


def test_first_person_becomes_admin_when_none_are_named(api, google):
    google.admin_emails = ""
    first, _ = sign_in(api, "first@midwestgames.com")
    second, _ = sign_in(api, "second@midwestgames.com")
    assert first.get("/api/auth/me").json()["user"]["role"] == "admin"
    assert second.get("/api/auth/me").json()["user"]["role"] == "viewer"
