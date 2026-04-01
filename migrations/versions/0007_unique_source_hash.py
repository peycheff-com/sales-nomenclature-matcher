"""Add unique constraint on source_hash to prevent catalog duplicates.

Revision ID: 0007_unique_source_hash
Revises: 0006_add_integrity_constraints
Create Date: 2026-04-01
"""

from alembic import op

revision = "0007_unique_source_hash"
down_revision = "0006_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deduplicate existing rows: keep the first (oldest) product per source_hash,
    # delete newer duplicates.
    op.execute("""
        DELETE FROM catalog_products
        WHERE product_id IN (
            SELECT product_id FROM (
                SELECT product_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_hash
                           ORDER BY created_at ASC
                       ) AS rn
                FROM catalog_products
                WHERE source_hash IS NOT NULL
            ) ranked
            WHERE rn > 1
        )
    """)

    op.create_index(
        "ix_catalog_products_source_hash",
        "catalog_products",
        ["source_hash"],
        unique=True,
        postgresql_where="source_hash IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_products_source_hash", table_name="catalog_products")
