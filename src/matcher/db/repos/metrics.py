from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import MatchRequest, MatchRequestItem, QualityReport


class MetricsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compute_quality_metrics(
        self,
        supplier_id: str | None = None,
        category_id: str | None = None,
    ) -> dict:
        """Compute quality metrics from reviewed items."""
        conditions = [MatchRequestItem.final_decision.is_not(None)]
        if supplier_id:
            conditions.append(MatchRequest.supplier_id == supplier_id)

        # Base query: reviewed items joined with requests
        base = (
            select(MatchRequestItem)
            .join(MatchRequest, MatchRequestItem.request_id == MatchRequest.request_id)
            .where(and_(*conditions))
        )

        # Total reviewed
        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(total_stmt)).scalar() or 0

        if total == 0:
            return {
                "total_cases": 0,
                "top1_accuracy": None,
                "top3_recall": None,
                "precision_at_1": None,
                "auto_match_false_positive_rate": None,
                "review_acceptance_rate": None,
                "avg_latency_ms": None,
            }

        # Top-1 accuracy: accepted / total_reviewed
        accepted_stmt = select(func.count()).select_from(
            select(MatchRequestItem)
            .join(
                MatchRequest,
                MatchRequestItem.request_id == MatchRequest.request_id,
            )
            .where(and_(*conditions, MatchRequestItem.final_decision == "accepted"))
            .subquery()
        )
        accepted = (await self.session.execute(accepted_stmt)).scalar() or 0

        # Auto-match false positive rate
        auto_conditions = [*conditions, MatchRequestItem.status == "auto_match"]
        auto_total_stmt = select(func.count()).select_from(
            select(MatchRequestItem)
            .join(
                MatchRequest,
                MatchRequestItem.request_id == MatchRequest.request_id,
            )
            .where(and_(*auto_conditions))
            .subquery()
        )
        auto_total = (await self.session.execute(auto_total_stmt)).scalar() or 0

        auto_fp_conditions = [
            *auto_conditions,
            MatchRequestItem.final_decision.in_(["corrected", "rejected"]),
        ]
        auto_fp_stmt = select(func.count()).select_from(
            select(MatchRequestItem)
            .join(
                MatchRequest,
                MatchRequestItem.request_id == MatchRequest.request_id,
            )
            .where(and_(*auto_fp_conditions))
            .subquery()
        )
        auto_fp = (await self.session.execute(auto_fp_stmt)).scalar() or 0

        # Review acceptance rate
        review_acceptance = accepted / total if total > 0 else None

        # Avg latency (ms) across completed requests
        latency_conditions = [
            MatchRequest.finished_at.is_not(None),
            MatchRequest.started_at.is_not(None),
        ]
        if supplier_id:
            latency_conditions.append(MatchRequest.supplier_id == supplier_id)
        latency_stmt = select(
            func.avg(
                func.extract("epoch", MatchRequest.finished_at - MatchRequest.started_at) * 1000
            )
        ).where(and_(*latency_conditions))
        avg_latency = (await self.session.execute(latency_stmt)).scalar()

        return {
            "total_cases": total,
            "top1_accuracy": round(accepted / total, 4) if total > 0 else None,
            "top3_recall": None,  # Requires candidate analysis — computed separately if needed
            "precision_at_1": round(accepted / auto_total, 4) if auto_total > 0 else None,
            "auto_match_false_positive_rate": (
                round(auto_fp / auto_total, 4) if auto_total > 0 else None
            ),
            "review_acceptance_rate": (
                round(review_acceptance, 4) if review_acceptance is not None else None
            ),
            "avg_latency_ms": (round(float(avg_latency), 1) if avg_latency else None),
        }

    async def save_quality_report(self, report: dict) -> QualityReport:
        obj = QualityReport(
            report_id=f"report_{uuid.uuid4().hex[:12]}",
            **report,
        )
        self.session.add(obj)
        await self.session.flush()
        return obj
