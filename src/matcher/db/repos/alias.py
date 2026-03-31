from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import CatalogAlias


class AliasRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_normalized_text(self, normalized_text: str) -> list[CatalogAlias]:
        stmt = select(CatalogAlias).where(
            CatalogAlias.normalized_alias_text == normalized_text,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_product_ids_by_text(self, normalized_text: str) -> set[str]:
        aliases = await self.find_by_normalized_text(normalized_text)
        return {a.product_id for a in aliases}
