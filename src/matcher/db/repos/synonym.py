from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import NormalizationSynonym


class SynonymRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_synonyms(
        self,
        domain: str | None = None,
        supplier_id: str | None = None,
        category_id: str | None = None,
    ) -> list[NormalizationSynonym]:
        """Find active synonyms matching given filters."""
        conditions = [NormalizationSynonym.is_active.is_(True)]
        if domain:
            conditions.append(NormalizationSynonym.domain == domain)
        if supplier_id:
            conditions.append(NormalizationSynonym.supplier_id == supplier_id)
        else:
            conditions.append(NormalizationSynonym.supplier_id.is_(None))
        if category_id:
            conditions.append(NormalizationSynonym.category_id == category_id)

        stmt = select(NormalizationSynonym).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def build_synonym_map(
        self,
        supplier_id: str | None = None,
    ) -> dict[str, str]:
        """Build a {normalized_source_text: target_text} lookup.

        Merges global synonyms (supplier_id IS NULL) with supplier-specific ones.
        Supplier-specific entries take precedence over global ones.
        """
        # Global synonyms
        global_syns = await self.find_synonyms(supplier_id=None)
        result: dict[str, str] = {s.normalized_source_text: s.target_text for s in global_syns}

        # Supplier-specific overrides
        if supplier_id:
            supplier_syns = await self.find_synonyms(supplier_id=supplier_id)
            for s in supplier_syns:
                result[s.normalized_source_text] = s.target_text

        return result
