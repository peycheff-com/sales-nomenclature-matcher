from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.api.deps import get_db
from matcher.auth.deps import get_current_user
from matcher.db.models import QualityReport, User
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


@router.get("/metrics/quality/history")
async def get_quality_history(
    supplier_id: str | None = Query(None),
    category_id: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get quality metrics history for trend analysis."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import and_

    since = datetime.now(UTC) - timedelta(days=days)
    conditions = [QualityReport.created_at >= since]
    if supplier_id:
        conditions.append(QualityReport.scope == "supplier")
        conditions.append(QualityReport.scope_value == supplier_id)
    elif category_id:
        conditions.append(QualityReport.scope == "category")
        conditions.append(QualityReport.scope_value == category_id)
    else:
        conditions.append(QualityReport.scope == "all")

    stmt = select(QualityReport).where(and_(*conditions)).order_by(QualityReport.created_at.asc())
    result = await db.execute(stmt)
    reports = result.scalars().all()

    return {
        "items": [
            {
                "report_id": r.report_id,
                "index_version_id": r.index_version_id,
                "top1_accuracy": float(r.top1_accuracy) if r.top1_accuracy else None,
                "top3_recall": float(r.top3_recall) if r.top3_recall else None,
                "precision_at_1": float(r.precision_at_1) if r.precision_at_1 else None,
                "auto_match_fp_rate": float(r.auto_match_fp_rate) if r.auto_match_fp_rate else None,
                "review_acceptance_rate": (
                    float(r.review_acceptance_rate) if r.review_acceptance_rate else None
                ),
                "total_cases": r.total_cases,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }
