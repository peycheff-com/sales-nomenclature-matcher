from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import require_role
from matcher.db.models import User
from matcher.db.repos.audit import AuditRepo

router = APIRouter(tags=["Audit"])


class AuditLogEntry(BaseModel):
    log_id: str
    action: str
    entity_type: str
    entity_id: str | None
    user_id: str | None
    username: str | None
    details: dict
    ip_address: str | None
    created_at: str | None


@router.get("/audit")
async def list_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """List audit log entries (admin only)."""
    repo = AuditRepo(db)
    logs, total = await repo.list_logs(
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            AuditLogEntry(
                log_id=entry.log_id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                user_id=entry.user_id,
                username=entry.username,
                details=entry.details,
                ip_address=entry.ip_address,
                created_at=entry.created_at.isoformat() if entry.created_at else None,
            )
            for entry in logs
        ],
        "total": total,
    }
