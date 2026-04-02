"""Add pending match status and persisted job metadata for recovery.

Revision ID: 0009_match_request_queue_recovery
Revises: 0008_audit_review_roles
Create Date: 2026-04-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_match_request_queue_recovery"
down_revision: str | None = "0008_audit_review_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "match_requests",
        sa.Column("job_name", sa.Text(), nullable=False, server_default="batch_match"),
    )
    op.add_column(
        "match_requests",
        sa.Column(
            "job_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'match_requests'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%status%'
    """)
    )
    for row in result:
        op.drop_constraint(row[0], "match_requests", type_="check")

    op.create_check_constraint(
        "ck_match_requests_status",
        "match_requests",
        "status in ('pending','queued','running','done','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_match_requests_status", "match_requests", type_="check")
    op.create_check_constraint(
        "ck_match_requests_status",
        "match_requests",
        "status in ('queued','running','done','failed')",
    )
    op.drop_column("match_requests", "job_payload_json")
    op.drop_column("match_requests", "job_name")
