"""People who have signed in, and their roles. Admins only."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Principal, require_admin
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active, "created_at": u.created_at, "last_login_at": u.last_login_at}


class UserUpdate(BaseModel):
    role: Literal["admin", "viewer"] | None = None
    active: bool | None = None


@router.get("")
def list_users(session: Session = Depends(get_session)):
    return [user_out(u) for u in session.scalars(select(User).order_by(User.role, User.email))]


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, who: Principal = Depends(require_admin), session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Person not found")
    losing_admin = user.role == "admin" and user.active and (body.role == "viewer" or body.active is False)
    if losing_admin:
        admins = session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True)))
        if admins <= 1:
            raise HTTPException(409, "There has to be at least one admin. Make someone else an admin first.")
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    session.commit()
    return user_out(user)
