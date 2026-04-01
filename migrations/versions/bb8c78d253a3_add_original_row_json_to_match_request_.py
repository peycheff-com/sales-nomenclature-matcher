"""Add original_row_json to match_request_items

Revision ID: bb8c78d253a3
Revises: 0003_system_settings
Create Date: 2026-04-01 03:04:23.333171

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bb8c78d253a3"
down_revision: str | Sequence[str] | None = "0003_system_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "match_request_items",
        sa.Column("original_row_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_request_items", "original_row_json")
