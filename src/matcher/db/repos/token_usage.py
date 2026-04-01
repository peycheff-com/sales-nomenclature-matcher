from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import TokenUsageLog


class TokenUsageRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_summary(
        self,
        days: int = 30,
        provider: str | None = None,
    ) -> dict:
        """Get aggregated token usage summary."""
        since = datetime.utcnow() - timedelta(days=days)

        # Base filter
        base = select(TokenUsageLog).where(TokenUsageLog.created_at >= since)
        if provider:
            base = base.where(TokenUsageLog.provider == provider)

        # Total aggregation
        totals_q = select(
            func.coalesce(func.sum(TokenUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(TokenUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(TokenUsageLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsageLog.estimated_cost_usd), 0).label("total_cost_usd"),
            func.count().label("api_calls"),
        ).where(TokenUsageLog.created_at >= since)
        if provider:
            totals_q = totals_q.where(TokenUsageLog.provider == provider)
        totals = (await self.session.execute(totals_q)).one()

        # By provider
        by_provider_q = select(
            TokenUsageLog.provider,
            func.sum(TokenUsageLog.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLog.estimated_cost_usd).label("cost_usd"),
            func.count().label("calls"),
        ).where(TokenUsageLog.created_at >= since).group_by(TokenUsageLog.provider)
        by_provider = (await self.session.execute(by_provider_q)).all()

        # By model
        by_model_q = select(
            TokenUsageLog.provider,
            TokenUsageLog.model,
            TokenUsageLog.operation,
            func.sum(TokenUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(TokenUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(TokenUsageLog.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLog.estimated_cost_usd).label("cost_usd"),
            func.count().label("calls"),
        ).where(TokenUsageLog.created_at >= since).group_by(
            TokenUsageLog.provider, TokenUsageLog.model, TokenUsageLog.operation
        )
        by_model = (await self.session.execute(by_model_q)).all()

        # Daily breakdown (last N days)
        daily_q = select(
            cast(TokenUsageLog.created_at, Date).label("date"),
            func.sum(TokenUsageLog.total_tokens).label("total_tokens"),
            func.sum(TokenUsageLog.estimated_cost_usd).label("cost_usd"),
        ).where(TokenUsageLog.created_at >= since).group_by(
            cast(TokenUsageLog.created_at, Date)
        ).order_by(cast(TokenUsageLog.created_at, Date))
        daily = (await self.session.execute(daily_q)).all()

        return {
            "period_days": days,
            "totals": {
                "prompt_tokens": int(totals.prompt_tokens),
                "completion_tokens": int(totals.completion_tokens),
                "total_tokens": int(totals.total_tokens),
                "total_cost_usd": float(totals.total_cost_usd),
                "api_calls": int(totals.api_calls),
            },
            "by_provider": [
                {
                    "provider": r.provider,
                    "total_tokens": int(r.total_tokens or 0),
                    "cost_usd": float(r.cost_usd or 0),
                    "calls": int(r.calls),
                }
                for r in by_provider
            ],
            "by_model": [
                {
                    "provider": r.provider,
                    "model": r.model,
                    "operation": r.operation,
                    "prompt_tokens": int(r.prompt_tokens or 0),
                    "completion_tokens": int(r.completion_tokens or 0),
                    "total_tokens": int(r.total_tokens or 0),
                    "cost_usd": float(r.cost_usd or 0),
                    "calls": int(r.calls),
                }
                for r in by_model
            ],
            "daily": [
                {
                    "date": str(r.date),
                    "total_tokens": int(r.total_tokens or 0),
                    "cost_usd": float(r.cost_usd or 0),
                }
                for r in daily
            ],
        }
