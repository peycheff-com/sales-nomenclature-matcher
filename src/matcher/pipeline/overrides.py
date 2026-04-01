from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class OverrideResult:
    """Result of supplier override lookup."""

    product_id: str
    mapping_type: str
    confidence: float


async def check_supplier_override(
    supplier_id: str | None,
    raw_text: str,
    normalized_text: str,
    article_hint: str | None,
    session: AsyncSession,
) -> OverrideResult | None:
    """Check if there's an exact supplier mapping for this query.

    Checks in order:
    1. supplier_sku exact
    2. supplier_article exact
    3. supplier_raw_text exact (previously confirmed)
    4. normalized_supplier_text match
    """
    if not supplier_id:
        return None

    result = await session.execute(
        text("""
            SELECT product_id, mapping_type, confidence
            FROM supplier_mappings
            WHERE supplier_id = :supplier_id
              AND is_active = true
              AND (
                  supplier_sku = :raw_text
                  OR supplier_article = :article_hint
                  OR supplier_raw_text = :raw_text
                  OR normalized_supplier_text = :normalized_text
              )
            ORDER BY
                CASE mapping_type
                    WHEN 'exact' THEN 1
                    WHEN 'approved' THEN 2
                    WHEN 'manual' THEN 3
                    WHEN 'learned' THEN 4
                END
            LIMIT 1
        """),
        {
            "supplier_id": supplier_id,
            "raw_text": raw_text,
            "article_hint": article_hint or "",
            "normalized_text": normalized_text,
        },
    )
    row = result.fetchone()
    if row:
        return OverrideResult(
            product_id=row[0],
            mapping_type=row[1],
            confidence=float(row[2]) if row[2] else 0.995,
        )
    return None
