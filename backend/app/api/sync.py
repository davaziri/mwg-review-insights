from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import SyncRunOut, SyncRunWithTitle
from app.config import get_settings
from app.db import get_session
from app.models import SyncRun, Title
from app.worker.runner import enqueue_all_active

router = APIRouter(prefix="/api", tags=["sync"])


@router.post("/sync/all", response_model=list[SyncRunOut])
def sync_all(session: Session = Depends(get_session)):
    return enqueue_all_active(session, get_settings(), trigger="manual")


@router.get("/sync-runs", response_model=list[SyncRunWithTitle])
def sync_runs(limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.execute(
        select(SyncRun, Title.name).join(Title, Title.id == SyncRun.title_id).order_by(SyncRun.id.desc()).limit(limit)
    )
    return [
        SyncRunWithTitle(**SyncRunOut.model_validate(run).model_dump(), title_name=name) for run, name in rows
    ]
