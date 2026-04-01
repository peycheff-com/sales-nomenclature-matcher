"""Add token_usage_log table for API consumption tracking.

Revision ID: 0005_token_usage
Revises: ede63bcb39f8
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_token_usage"
down_revision = "ede63bcb39f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_usage_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Text(), sa.ForeignKey("match_requests.request_id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation", sa.Text(), nullable=False, comment="embed | rerank | llm_rerank | agent"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_usage_log_request_id", "token_usage_log", ["request_id"])
    op.create_index("ix_token_usage_log_created_at", "token_usage_log", ["created_at"])
    op.create_index("ix_token_usage_log_provider", "token_usage_log", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_log_provider")
    op.drop_index("ix_token_usage_log_created_at")
    op.drop_index("ix_token_usage_log_request_id")
    op.drop_table("token_usage_log")
