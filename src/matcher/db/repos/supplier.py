from __future__ import annotations

import uuid

from sqlalchemy import and_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import SupplierMapping, SupplierProfile


class SupplierRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_suppliers(self, active_only: bool = True) -> list[SupplierProfile]:
        stmt = select(SupplierProfile)
        if active_only:
            stmt = stmt.where(SupplierProfile.is_active == True)  # noqa: E712
        stmt = stmt.order_by(SupplierProfile.supplier_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_supplier(self, supplier_id: str) -> SupplierProfile | None:
        result = await self.session.execute(
            select(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
        )
        return result.scalar_one_or_none()

    async def create_supplier(self, supplier_id: str, name: str, strict_mode: bool = False) -> SupplierProfile:
        supplier = SupplierProfile(
            supplier_id=supplier_id,
            supplier_name=name,
            strict_mode=strict_mode,
            is_active=True,
        )
        self.session.add(supplier)
        await self.session.flush()
        return supplier

    async def update_supplier(self, supplier_id: str, **kwargs: object) -> SupplierProfile | None:
        supplier = await self.get_supplier(supplier_id)
        if not supplier:
            return None
        for k, v in kwargs.items():
            if hasattr(supplier, k):
                setattr(supplier, k, v)
        await self.session.flush()
        return supplier

    async def create_mapping(self, supplier_id: str, data: dict) -> SupplierMapping:
        mapping = SupplierMapping(
            mapping_id=f"map_{uuid.uuid4().hex[:12]}",
            supplier_id=supplier_id,
            **data,
        )
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def find_mapping(
        self,
        supplier_id: str,
        *,
        raw_text: str | None = None,
        normalized_text: str | None = None,
        article: str | None = None,
    ) -> SupplierMapping | None:
        """Find an active supplier mapping by various criteria."""
        stmt = select(SupplierMapping).where(
            and_(
                SupplierMapping.supplier_id == supplier_id,
                SupplierMapping.is_active == True,  # noqa: E712
            )
        )
        if article:
            stmt = stmt.where(SupplierMapping.supplier_article == article)
        elif normalized_text:
            stmt = stmt.where(SupplierMapping.normalized_supplier_text == normalized_text)
        elif raw_text:
            stmt = stmt.where(SupplierMapping.supplier_raw_text == raw_text)
        else:
            return None
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def delete_supplier(self, supplier_id: str) -> bool:
        result = await self.session.execute(
            delete(SupplierProfile).where(SupplierProfile.supplier_id == supplier_id)
        )
        return result.rowcount > 0

    async def get_supplier_mappings(
        self, supplier_id: str, limit: int = 50, offset: int = 0
    ) -> list[SupplierMapping]:
        stmt = (
            select(SupplierMapping)
            .where(SupplierMapping.supplier_id == supplier_id)
            .order_by(SupplierMapping.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
