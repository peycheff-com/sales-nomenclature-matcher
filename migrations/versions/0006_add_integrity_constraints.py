"""Add unique constraint on supplier_mappings and SET NULL FK on match_requests.supplier_id.

Revision ID: 0006_integrity
Revises: 0005_token_usage
Create Date: 2026-04-01
"""

from alembic import op
from sqlalchemy import text

revision = "0006_integrity"
down_revision = "0005_token_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Unique constraint on supplier_mappings(supplier_id, supplier_raw_text)
    op.create_unique_constraint(
        "uq_supplier_mapping_text",
        "supplier_mappings",
        ["supplier_id", "supplier_raw_text"],
    )

    # 2. Recreate match_requests.supplier_id FK with ondelete="SET NULL"
    op.drop_constraint(
        "match_requests_supplier_id_fkey",
        "match_requests",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "match_requests_supplier_id_fkey",
        "match_requests",
        "supplier_profiles",
        ["supplier_id"],
        ["supplier_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Reverse FK back to original (no ondelete)
    op.drop_constraint(
        "match_requests_supplier_id_fkey",
        "match_requests",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "match_requests_supplier_id_fkey",
        "match_requests",
        "supplier_profiles",
        ["supplier_id"],
        ["supplier_id"],
    )

    # Drop unique constraint
    op.drop_constraint(
        "uq_supplier_mapping_text",
        "supplier_mappings",
        type_="unique",
    )
