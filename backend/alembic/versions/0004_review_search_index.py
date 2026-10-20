"""review search index

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20 04:10:00
"""
from collections.abc import Sequence

from alembic import op

from app.search import drop_search_index, install_search_index

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    install_search_index(op.get_bind())


def downgrade() -> None:
    drop_search_index(op.get_bind())
