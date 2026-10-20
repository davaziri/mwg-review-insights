"""Sign in with Google, see who is signed in, and sign out."""

import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    SIGNIN_COOKIE,
    base_url,
    current_principal,
    exchange_code,
    google_login_url,
    sign,
    sign_in,
    sign_in_problem,
    unsign,
)
from app.config import get_settings
from app.db import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])

SIGNIN_SECONDS = 600


def _safe_next(value: str | None) -> str:
    """Only paths inside this app, so the sign-in can't be used to send people elsewhere."""
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


def _cookie_args(request: Request) -> dict:
    secure = base_url(request, get_settings()).startswith("https://")
    return {"httponly": True, "samesite": "lax", "secure": secure, "path": "/"}


def _fail(message: str) -> RedirectResponse:
    resp = RedirectResponse(f"/?signin_error={quote(message)}", status_code=302)
    resp.delete_cookie(SIGNIN_COOKIE, path="/")
    return resp


@router.get("/me")
def me(request: Request, session: Session = Depends(get_session)):
    settings = get_settings()
    who = current_principal(request, session, settings)
    return {
        "mode": settings.auth_mode,
        "user": None if who is None else {"id": who.id, "email": who.email, "name": who.name, "role": who.role},
        "problem": sign_in_problem(settings),
    }


@router.get("/login")
def login(request: Request, next: str | None = None):
    settings = get_settings()
    problem = sign_in_problem(settings)
    if problem:
        return _fail(problem)
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    redirect_uri = f"{base_url(request, settings)}/api/auth/callback"
    resp = RedirectResponse(google_login_url(settings, redirect_uri, state, nonce), status_code=302)
    signed = sign({"state": state, "nonce": nonce, "next": _safe_next(next), "exp": time.time() + SIGNIN_SECONDS}, settings)
    resp.set_cookie(SIGNIN_COOKIE, signed, max_age=SIGNIN_SECONDS, **_cookie_args(request))
    return resp


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, session: Session = Depends(get_session)):
    settings = get_settings()
    pending = unsign(request.cookies.get(SIGNIN_COOKIE), settings)
    if error:
        return _fail("Sign-in was canceled.")
    if not pending or not code or not state or not secrets.compare_digest(state, str(pending.get("state", ""))):
        return _fail("The sign-in expired or came from somewhere else. Please try again.")
    try:
        claims = exchange_code(code, f"{base_url(request, settings)}/api/auth/callback", settings, pending["nonce"])
    except ValueError as exc:
        return _fail(str(exc))
    user = sign_in(session, settings, claims["email"], claims.get("name"))
    if not user.active:
        return _fail("Your access has been turned off. Ask an admin to turn it back on.")
    days = settings.session_days
    resp = RedirectResponse(_safe_next(pending.get("next")), status_code=302)
    resp.set_cookie(SESSION_COOKIE, sign({"uid": user.id, "exp": time.time() + days * 86_400}, settings), max_age=days * 86_400, **_cookie_args(request))
    resp.delete_cookie(SIGNIN_COOKIE, path="/")
    return resp


@router.post("/logout")
def logout(request: Request):
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
