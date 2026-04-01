from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import CatalogAlias, CatalogEmbedding, CatalogProduct, IndexVersion


class CatalogRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_product(self, product_id: str) -> CatalogProduct | None:
        result = await self.session.execute(
            select(CatalogProduct).where(CatalogProduct.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def search_products(
        self, query: str | None = None, limit: int = 50
    ) -> list[CatalogProduct]:
        """Search products by name/article."""
        stmt = select(CatalogProduct).where(CatalogProduct.is_active)
        if query:
            search_term = f"%{query}%"
            stmt = stmt.where(
                or_(
                    CatalogProduct.name.ilike(search_term),
                    CatalogProduct.article.ilike(search_term),
                    CatalogProduct.brand.ilike(search_term),
                )
            )
        stmt = stmt.order_by(CatalogProduct.name).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_products(self, items: list[dict]) -> int:
        """Bulk upsert from transformer dicts. Returns count of affected rows."""
        if not items:
            return 0
        stmt = insert(CatalogProduct).values(items)
        stmt = stmt.on_conflict_do_update(
            index_elements=["product_id"],
            set_={
                "name": stmt.excluded.name,
                "full_name": stmt.excluded.full_name,
                "article": stmt.excluded.article,
                "brand": stmt.excluded.brand,
                "normalized_name": stmt.excluded.normalized_name,
                "normalized_brand": stmt.excluded.normalized_brand,
                "search_document": stmt.excluded.search_document,
                "source_hash": stmt.excluded.source_hash,
                "source_version": stmt.excluded.source_version,
                "is_active": stmt.excluded.is_active,
            },
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count()).where(CatalogProduct.is_active == True)  # noqa: E712
        )
        return result.scalar() or 0

    async def get_products_needing_embedding(
        self, model: str, version: str, limit: int = 100, offset: int = 0
    ) -> list[CatalogProduct]:
        """Get active products that don't have embeddings for the given model/version."""
        subq = select(CatalogEmbedding.product_id).where(
            and_(
                CatalogEmbedding.embedding_model == model,
                CatalogEmbedding.embedding_version == version,
            )
        )
        stmt = (
            select(CatalogProduct)
            .where(
                and_(
                    CatalogProduct.is_active == True,  # noqa: E712
                    ~CatalogProduct.product_id.in_(subq),
                )
            )
            .order_by(CatalogProduct.product_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_embedding(
        self,
        product_id: str,
        model: str,
        version: str,
        vector: list[float],
    ) -> None:
        stmt = insert(CatalogEmbedding).values(
            product_id=product_id,
            embedding_model=model,
            embedding_version=version,
            embedding_vector=vector,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["product_id"],
            set_={
                "embedding_model": model,
                "embedding_version": version,
                "embedding_vector": vector,
            },
        )
        await self.session.execute(stmt)

    async def create_alias(
        self,
        product_id: str,
        alias_text: str,
        normalized_text: str,
        alias_type: str = "user_added",
        created_by: str = "system",
    ) -> CatalogAlias:
        alias = CatalogAlias(
            alias_id=f"alias_{uuid.uuid4().hex[:12]}",
            product_id=product_id,
            alias_text=alias_text,
            normalized_alias_text=normalized_text,
            alias_type=alias_type,
            created_by=created_by,
        )
        self.session.add(alias)
        await self.session.flush()
        return alias

    async def delete_product(self, product_id: str) -> bool:
        """Deletes a product by ID. Cascades via foreign keys."""
        stmt = select(CatalogProduct).where(CatalogProduct.product_id == product_id)
        result = await self.session.execute(stmt)
        product = result.scalar_one_or_none()
        if product:
            await self.session.delete(product)
            await self.session.flush()
            return True
        return False

    async def delete_all_products(self) -> int:
        """Deletes ALL products by truncating the table, which cascades."""
        from sqlalchemy import text

        await self.session.execute(text("TRUNCATE TABLE catalog_products CASCADE"))
        return 1

    # ------------------------------------------------------------------
    # Index versions
    # ------------------------------------------------------------------

    async def list_index_versions(self) -> list[IndexVersion]:
        """List all index versions, newest first."""
        stmt = select(IndexVersion).order_by(IndexVersion.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def activate_index_version(self, version_id: str) -> bool:
        """Activate a specific index version, deactivating all others."""
        from datetime import UTC, datetime

        from sqlalchemy import update

        target = await self.session.execute(
            select(IndexVersion).where(IndexVersion.index_version_id == version_id)
        )
        version = target.scalar_one_or_none()
        if not version:
            return False

        # Deactivate all
        await self.session.execute(
            update(IndexVersion).values(is_active=False)
        )
        # Activate target
        await self.session.execute(
            update(IndexVersion)
            .where(IndexVersion.index_version_id == version_id)
            .values(is_active=True, activated_at=func.now())
        )
        return True
