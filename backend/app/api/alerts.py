"""The run log's alerts, and a test message to check Slack and email are set up."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import channels, send_test
from app.auth import actor
from app.config import get_settings
from app.db import get_session
from app.models import Alert, Title

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def alert_out(a: Alert, title_name: str | None) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "title_id": a.title_id,
        "title_name": title_name,
        "subject": a.subject,
        "body": a.body,
        "channels": a.channels,
        "error": a.error,
        "created_at": a.created_at,
    }


@router.get("")
def list_alerts(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.execute(select(Alert, Title.name).outerjoin(Title, Title.id == Alert.title_id).order_by(Alert.id.desc()).limit(limit))
    return {"channels": channels(get_settings()), "alerts": [alert_out(a, name) for a, name in rows]}


@router.post("/test")
def test_alert(request: Request, session: Session = Depends(get_session)):
    """Send a test message to every channel that is set up (admins only, like every change)."""
    return alert_out(send_test(session, get_settings(), actor(request)), None)
