"""Add must_change_password to users table.

Revision ID: 0004_must_change_password
Revises: bb8c78d253a3
Create Date: 2026-04-01
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_must_change_password"
down_revision: str | None = "bb8c78d253a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN must_change_password")
