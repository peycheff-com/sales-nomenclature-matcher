"""Add audit_log table, review_notes column, expand user roles, golden label versioning.

Revision ID: 0008_audit_review_roles
Revises: 0007_unique_source_hash
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_audit_review_roles"
down_revision = "0007_unique_source_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add review_notes to match_request_items
    op.add_column(
        "match_request_items",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )

    # 2. Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.Text(), primary_key=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("details", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_audit_action", "audit_log", ["action"])
    op.create_index("idx_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("idx_audit_user", "audit_log", ["user_id"])
    op.create_index("idx_audit_created", "audit_log", ["created_at"])

    # 3. Expand user role constraint to include reviewer and catalog_operator
    # Drop existing check constraint (name may vary across environments)
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'users'::regclass AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%role%'
    """)
    )
    for row in result:
        op.drop_constraint(row[0], "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role in ('admin','operator','viewer','reviewer','catalog_operator')",
    )

    # 4. Add version and is_active to golden_labels
    op.add_column(
        "golden_labels",
        sa.Column("version", sa.Text(), nullable=True),
    )
    op.add_column(
        "golden_labels",
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("golden_labels", "is_active")
    op.drop_column("golden_labels", "version")

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role in ('admin','operator','viewer')",
    )

    op.drop_index("idx_audit_created", table_name="audit_log")
    op.drop_index("idx_audit_user", table_name="audit_log")
    op.drop_index("idx_audit_entity", table_name="audit_log")
    op.drop_index("idx_audit_action", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_column("match_request_items", "review_notes")
