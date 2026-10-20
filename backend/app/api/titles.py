from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AppStats,
    SnapshotOut,
    SyncRequest,
    SyncRunOut,
    TitleCreate,
    TitleOut,
    TitleUpdate,
)
from app.auth import actor
from app.config import get_settings
from app.db import get_session
from app.models import Review, ReviewSnapshot, SyncRun, Title
from app.models.sync import ACTIVE_STATUSES
from app.steam.appdetails import refresh_appdetails
from app.steam.client import SteamClient
from app.steam.sync import enqueue_sync, latest_run
from app.timeutil import utcnow

router = APIRouter(prefix="/api/titles", tags=["titles"])


def _get_title(session: Session, title_id: int) -> Title:
    title = session.get(Title, title_id)
    if title is None:
        raise HTTPException(404, "Title not found")
    return title


def _title_out(session: Session, title: Title) -> TitleOut:
    counts = {
        app_id: (total, positive)
        for app_id, total, positive in session.execute(
            select(
                Review.app_id,
                func.count(),
                func.sum(case((Review.voted_up.is_(True), 1), else_=0)),
            )
            .where(Review.title_id == title.id, Review.deleted_at.is_(None))
            .group_by(Review.app_id)
        )
    }
    apps = []
    for app_id in title.app_ids:
        snapshot = session.scalar(
            select(ReviewSnapshot)
            .where(ReviewSnapshot.title_id == title.id, ReviewSnapshot.app_id == app_id)
            .order_by(ReviewSnapshot.snapshot_date.desc())
            .limit(1)
        )
        last = latest_run(session, title.id, app_id, status=["succeeded", "failed"])
        active = latest_run(session, title.id, app_id, status=list(ACTIVE_STATUSES))
        total, positive = counts.get(app_id, (0, 0))
        apps.append(
            AppStats(
                app_id=app_id,
                is_demo=app_id != title.steam_app_id,
                stored_reviews=total or 0,
                stored_positive=positive or 0,
                latest_snapshot=SnapshotOut.model_validate(snapshot) if snapshot else None,
                last_run=SyncRunOut.model_validate(last) if last else None,
                active_run=SyncRunOut.model_validate(active) if active else None,
            )
        )
    last_ok = latest_run(session, title.id, title.steam_app_id, status=["succeeded"])
    out = TitleOut.model_validate(title)
    out.apps = apps
    out.last_synced_at = last_ok.finished_at if last_ok else None
    return out


@router.get("", response_model=list[TitleOut])
def list_titles(include_archived: bool = False, session: Session = Depends(get_session)):
    query = select(Title).order_by(Title.archived_at.is_not(None), Title.id)
    if not include_archived:
        query = query.where(Title.archived_at.is_(None))
    return [_title_out(session, t) for t in session.scalars(query)]


@router.get("/{title_id}", response_model=TitleOut)
def get_title(title_id: int, session: Session = Depends(get_session)):
    return _title_out(session, _get_title(session, title_id))


@router.post("", response_model=TitleOut, status_code=201)
def create_title(body: TitleCreate, request: Request, session: Session = Depends(get_session)):
    if session.scalar(select(Title).where(Title.steam_app_id == body.steam_app_id)):
        raise HTTPException(409, f"Steam app {body.steam_app_id} is already tracked")
    title = Title(
        steam_app_id=body.steam_app_id,
        demo_app_id=body.demo_app_id,
        status=body.status,
        notes=body.notes,
        name=body.name or f"Steam app {body.steam_app_id}",
    )
    session.add(title)
    session.flush()
    # Fill in name, header image, release date and developer right away. If Steam can't be
    # reached the title is still saved and the next sync fills these in.
    with SteamClient.from_settings(get_settings(), max_retries=1) as client:
        refresh_appdetails(title, client)
    if body.name:
        title.name = body.name
    session.commit()
    if body.sync_now:
        enqueue_sync(session, get_settings(), title, trigger="manual", requested_by=actor(request))
    return _title_out(session, title)


@router.patch("/{title_id}", response_model=TitleOut)
def update_title(title_id: int, body: TitleUpdate, session: Session = Depends(get_session)):
    title = _get_title(session, title_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(title, field, value)
    session.commit()
    return _title_out(session, title)


@router.post("/{title_id}/archive", response_model=TitleOut)
def archive_title(title_id: int, session: Session = Depends(get_session)):
    title = _get_title(session, title_id)
    if title.archived_at is None:
        title.archived_at = utcnow()
        session.commit()
    return _title_out(session, title)


@router.post("/{title_id}/unarchive", response_model=TitleOut)
def unarchive_title(title_id: int, session: Session = Depends(get_session)):
    title = _get_title(session, title_id)
    title.archived_at = None
    session.commit()
    return _title_out(session, title)


@router.delete("/{title_id}", status_code=204)
def delete_title(title_id: int, session: Session = Depends(get_session)):
    """Remove a title and everything stored for it. Archive instead to keep the history."""
    title = _get_title(session, title_id)
    busy = session.scalar(
        select(SyncRun.id).where(SyncRun.title_id == title.id, SyncRun.status.in_(ACTIVE_STATUSES)).limit(1)
    )
    if busy:
        raise HTTPException(409, "A sync is queued or running for this title. Try again when it finishes.")
    session.delete(title)
    session.commit()


@router.post("/{title_id}/sync", response_model=list[SyncRunOut])
def sync_title(title_id: int, request: Request, body: SyncRequest | None = None, session: Session = Depends(get_session)):
    title = _get_title(session, title_id)
    if title.archived_at is not None:
        raise HTTPException(409, "Unarchive this title before syncing it")
    mode = body.mode if body else None
    return enqueue_sync(session, get_settings(), title, trigger="manual", mode=mode, requested_by=actor(request))


@router.get("/{title_id}/sync-runs", response_model=list[SyncRunOut])
def title_sync_runs(
    title_id: int, limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
):
    _get_title(session, title_id)
    return session.scalars(
        select(SyncRun).where(SyncRun.title_id == title_id).order_by(SyncRun.id.desc()).limit(limit)
    ).all()
