from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user
from matcher.db.models import User
from matcher.db.repos.metrics import MetricsRepo
from matcher.db.repos.token_usage import TokenUsageRepo
from matcher.schemas.supplier import QualityMetrics

router = APIRouter(tags=["Metrics"])


@router.get("/metrics/quality", response_model=QualityMetrics)
async def get_quality_metrics(
    supplier_id: str | None = Query(None),
    category_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = MetricsRepo(db)
    metrics = await repo.compute_quality_metrics(
        supplier_id=supplier_id,
        category_id=category_id,
    )
    return QualityMetrics(**metrics)


@router.get("/metrics/tokens")
async def get_token_usage(
    days: int = Query(30, ge=1, le=365),
    provider: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = TokenUsageRepo(db)
    return await repo.get_summary(days=days, provider=provider)
