"""Sign-in and roles.

People sign in with a Google account on one of the allowed domains. Viewers can browse and export;
admins can also sync, edit codebooks, run analyses and manage people. One rule covers the whole
API: reading needs a signed-in person, and anything that changes data needs an admin.

The session is a cookie holding the person's id and an expiry, signed with HMAC-SHA256, so it
can't be forged or edited. In "local" mode (for running on your own computer) sign-in is off and
everyone is treated as an admin.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User
from app.timeutil import utcnow

SESSION_COOKIE = "mwg_session"
SIGNIN_COOKIE = "mwg_signin"
# Every request that changes something must carry this header. A form on another website can't
# add it, so a signed-in admin can't be tricked into changing data from somewhere else.
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "mwg"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Principal:
    id: int | None
    email: str
    name: str | None
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


LOCAL_PRINCIPAL = Principal(None, "local", "Local user", "admin")


# Signing


@lru_cache
def _secret_from_file(path: str) -> bytes:
    file = Path(path)
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(secrets.token_urlsafe(48))
        file.chmod(0o600)
    return file.read_text().strip().encode()


def _secret(settings: Settings) -> bytes:
    if settings.session_secret:
        return settings.session_secret.encode()
    return _secret_from_file(str(settings.data_dir / ".session_secret"))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(data: dict, settings: Settings) -> str:
    payload = _b64(json.dumps(data, separators=(",", ":")).encode())
    mac = hmac.new(_secret(settings), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64(mac)}"


def unsign(value: str | None, settings: Settings) -> dict | None:
    """The signed data, or None if the value was tampered with, malformed or has expired."""
    if not value or value.count(".") != 1:
        return None
    payload, mac = value.split(".")
    expected = hmac.new(_secret(settings), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_unb64(mac), expected):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time():
        return None
    return data


# Who is asking


def email_allowed(email: str, settings: Settings) -> bool:
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    return bool(domain) and domain in settings.allowed_domain_list


def current_principal(request: Request, session: Session, settings: Settings) -> Principal | None:
    if settings.auth_mode == "local":
        return LOCAL_PRINCIPAL
    data = unsign(request.cookies.get(SESSION_COOKIE), settings)
    if not data:
        return None
    user = session.get(User, data.get("uid"))
    # Someone turned off by an admin, or whose domain is no longer allowed, is signed out.
    if user is None or not user.active or not email_allowed(user.email, settings):
        return None
    return Principal(user.id, user.email, user.name, user.role)


def access(request: Request, session: Session = Depends(get_session)) -> None:
    """Applied to every route. Pages and sign-in are open; the API needs a signed-in person, and
    changing anything needs an admin."""
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/health" or path.startswith("/api/auth/"):
        return
    settings = get_settings()
    who = current_principal(request, session, settings)
    if who is None:
        raise HTTPException(401, "Sign in to continue.")
    request.state.principal = who
    if request.method not in SAFE_METHODS:
        if settings.auth_mode == "google" and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "This request came from outside the app.")
        if not who.is_admin:
            raise HTTPException(403, "Only admins can do this. Ask an admin if you need access.")


def require_admin(request: Request) -> Principal:
    who: Principal | None = getattr(request.state, "principal", None)
    if who is None or not who.is_admin:
        raise HTTPException(403, "Only admins can do this.")
    return who


def actor(request: Request) -> str:
    """Who to record as having done something."""
    who: Principal | None = getattr(request.state, "principal", None)
    return who.email if who else "unknown"


# Google sign-in


def base_url(request: Request, settings: Settings) -> str:
    return (settings.public_url or str(request.base_url)).rstrip("/")


def sign_in_problem(settings: Settings) -> str | None:
    """Why Google sign-in can't work yet, in words for whoever sets the app up."""
    if settings.auth_mode != "google":
        return None
    missing = [name for name, value in (("GOOGLE_CLIENT_ID", settings.google_client_id), ("GOOGLE_CLIENT_SECRET", settings.google_client_secret), ("ALLOWED_DOMAINS", settings.allowed_domains.strip())) if not value]
    if missing:
        return f"Sign-in isn't set up yet: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing from the settings."
    return None


def google_login_url(settings: Settings, redirect_uri: str, state: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    domains = settings.allowed_domain_list
    if len(domains) == 1:
        params["hd"] = domains[0]  # Google shows only accounts on this domain
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _claims(id_token: str) -> dict:
    """The ID token's claims. Its signature isn't checked here: the token comes straight from
    Google's token endpoint over HTTPS in exchange for our client secret, which Google's
    documentation says is enough to trust it."""
    try:
        return json.loads(_unb64(id_token.split(".")[1]))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Google sent an ID token that could not be read.") from exc


def exchange_code(code: str, redirect_uri: str, settings: Settings, nonce: str, client: httpx.Client | None = None) -> dict:
    """Trade the sign-in code for the person's verified Google identity. Raises ValueError with a
    message fit to show if anything doesn't check out."""
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    finally:
        if own:
            client.close()
    if resp.status_code != 200 or "id_token" not in resp.json():
        raise ValueError("Google didn't accept the sign-in. Please try again.")
    claims = _claims(resp.json()["id_token"])
    if claims.get("iss") not in GOOGLE_ISSUERS or claims.get("aud") != settings.google_client_id:
        raise ValueError("The sign-in wasn't meant for this app.")
    if claims.get("exp", 0) < time.time() or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("The sign-in expired. Please try again.")
    email = str(claims.get("email", "")).lower()
    if not claims.get("email_verified") or not email_allowed(email, settings):
        raise ValueError(f"{email or 'That account'} can't sign in here. Use your work Google account.")
    hd = str(claims.get("hd", "")).lower()
    if hd != email.rsplit("@", 1)[-1]:
        raise ValueError("Sign in with your work Google account, not a personal one.")
    return claims


def sign_in(session: Session, settings: Settings, email: str, name: str | None) -> User:
    """Create or update the person. ADMIN_EMAILS are always admins; with none configured, the
    first person to sign in becomes an admin so someone can manage the others."""
    email = email.lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        no_admins = not session.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
        first_admin = not settings.admin_email_list and no_admins
        user = User(email=email, role="admin" if first_admin else "viewer")
        session.add(user)
    if email in settings.admin_email_list:
        user.role = "admin"
    user.name = name or user.name
    user.last_login_at = utcnow()
    session.commit()
    return user
