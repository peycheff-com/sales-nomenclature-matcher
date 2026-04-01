"""
Token usage tracking for LLM/embedding/rerank API calls.

Usage:
    tracker = TokenTracker(request_id="req_123")
    tracker.record("embed", "openai", "text-embedding-3-large", prompt_tokens=500)
    tracker.record(
        "llm_rerank", "openrouter", "gpt-4o-mini",
        prompt_tokens=1200, completion_tokens=300,
    )
    await tracker.flush(session)  # Persist all accumulated records to DB
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import TokenUsageLog

logger = logging.getLogger(__name__)

# Hardcoded fallback defaults in case the config file is missing.
_FALLBACK_DEFAULT_COST: dict[str, float] = {"prompt": 0.50, "completion": 1.50}


def _load_pricing() -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Load token pricing from configs/token_pricing.yaml.

    Returns (model_costs, default_cost). Falls back to built-in defaults
    if the YAML file is missing or cannot be parsed.
    """
    config_path = Path(__file__).resolve().parents[3] / "configs" / "token_pricing.yaml"
    try:
        import yaml  # noqa: E402 - local import to keep yaml optional at top-level

        with open(config_path) as f:
            data = yaml.safe_load(f)
        models = {
            str(k): {"prompt": float(v["prompt"]), "completion": float(v["completion"])}
            for k, v in data.get("models", {}).items()
        }
        default_section = data.get("default", {})
        fallback_p = _FALLBACK_DEFAULT_COST["prompt"]
        fallback_c = _FALLBACK_DEFAULT_COST["completion"]
        default = {
            "prompt": float(default_section.get("prompt", fallback_p)),
            "completion": float(default_section.get("completion", fallback_c)),
        }
        logger.debug("Loaded token pricing from %s (%d models)", config_path, len(models))
        return models, default
    except FileNotFoundError:
        logger.warning("Token pricing config not found at %s, using built-in defaults", config_path)
        return {}, _FALLBACK_DEFAULT_COST.copy()
    except Exception as e:
        logger.warning("Failed to load token pricing config: %s, using built-in defaults", e)
        return {}, _FALLBACK_DEFAULT_COST.copy()


COST_PER_1M, DEFAULT_COST = _load_pricing()


@dataclass
class _TokenRecord:
    operation: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal
    created_at: datetime


@dataclass
class TokenTracker:
    """Accumulates token usage records and flushes them to the database."""

    request_id: str | None = None
    _records: list[_TokenRecord] = field(default_factory=list)

    def record(
        self,
        operation: str,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        """Record a single API call's token usage."""
        total = total_tokens if total_tokens is not None else prompt_tokens + completion_tokens
        cost = _estimate_cost(model, prompt_tokens, completion_tokens)

        self._records.append(
            _TokenRecord(
                operation=operation,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated_cost_usd=cost,
                created_at=datetime.utcnow(),
            )
        )

    async def flush(self, session: AsyncSession) -> None:
        """Persist all accumulated records to the token_usage_log table."""
        if not self._records:
            return

        values = [
            {
                "request_id": self.request_id,
                "operation": r.operation,
                "provider": r.provider,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "estimated_cost_usd": r.estimated_cost_usd,
                "created_at": r.created_at,
            }
            for r in self._records
        ]
        try:
            await session.execute(insert(TokenUsageLog), values)
            await session.flush()
            logger.debug(f"Flushed {len(values)} token usage records for request={self.request_id}")
        except Exception as e:
            logger.warning(f"Failed to flush token usage records: {e}")
        finally:
            self._records.clear()

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self._records)

    @property
    def total_cost(self) -> Decimal:
        return sum(r.estimated_cost_usd for r in self._records)


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimate cost in USD based on known pricing."""
    # Try exact model match first, then prefix match
    pricing = COST_PER_1M.get(model)
    if not pricing:
        for key in COST_PER_1M:
            if key in model or model in key:
                pricing = COST_PER_1M[key]
                break
    if not pricing:
        pricing = DEFAULT_COST

    cost = (
        prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]
    ) / 1_000_000
    return Decimal(str(round(cost, 6)))
