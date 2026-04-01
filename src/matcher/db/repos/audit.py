from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import AuditLog


class AuditRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        user_id: str | None = None,
        username: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            log_id=f"audit_{uuid.uuid4().hex[:12]}",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            username=username,
            details=details or {},
            ip_address=ip_address,
        )
        self.session.add(entry)
        return entry

    async def list_logs(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        conditions = []
        if entity_type:
            conditions.append(AuditLog.entity_type == entity_type)
        if entity_id:
            conditions.append(AuditLog.entity_id == entity_id)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if action:
            conditions.append(AuditLog.action == action)

        where = and_(*conditions) if conditions else True

        from sqlalchemy import func

        count_result = await self.session.execute(select(func.count(AuditLog.log_id)).where(where))
        total = count_result.scalar() or 0

        stmt = (
            select(AuditLog)
            .where(where)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
