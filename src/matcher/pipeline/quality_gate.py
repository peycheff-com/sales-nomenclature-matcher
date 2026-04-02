"""Quality gate for index activation.

Evaluates the golden set against a new index before activation.
Blocks activation if quality regresses beyond configurable thresholds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.repos.metrics import MetricsRepo

logger = logging.getLogger(__name__)

# Default regression thresholds
MAX_ACCURACY_DROP = 0.02  # 2% top-1 accuracy drop
MAX_FP_INCREASE = 0.01  # 1% false-positive rate increase
MAX_RECALL_DROP = 0.03  # 3% top-3 recall drop


@dataclass
class GateResult:
    passed: bool
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    current_metrics: dict = field(default_factory=dict)
    previous_metrics: dict = field(default_factory=dict)


async def evaluate_quality_gate(
    session: AsyncSession,
    *,
    max_accuracy_drop: float = MAX_ACCURACY_DROP,
    max_fp_increase: float = MAX_FP_INCREASE,
    max_recall_drop: float = MAX_RECALL_DROP,
) -> GateResult:
    """Compare current quality metrics against thresholds.

    Returns a GateResult indicating whether the gate passes.
    This is called after reindex to decide whether to activate the new index.
    """
    metrics_repo = MetricsRepo(session)
    current = await metrics_repo.compute_quality_metrics()

    result = GateResult(
        passed=True,
        current_metrics=current,
    )

    # If no golden set data, gate passes (can't evaluate)
    if current.get("total_cases", 0) == 0:
        logger.info("Quality gate: no golden set data, passing by default")
        return result

    # Load the most recent saved quality report for comparison
    from sqlalchemy import select

    from matcher.db.models import QualityReport

    stmt = (
        select(QualityReport)
        .where(QualityReport.scope == "all")
        .order_by(QualityReport.created_at.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    prev_report = res.scalar_one_or_none()

    if not prev_report:
        logger.info("Quality gate: no previous report, passing by default")
        return result

    prev = {
        "top1_accuracy": float(prev_report.top1_accuracy) if prev_report.top1_accuracy else None,
        "top3_recall": float(prev_report.top3_recall) if prev_report.top3_recall else None,
        "auto_match_fp_rate": (
            float(prev_report.auto_match_fp_rate) if prev_report.auto_match_fp_rate else None
        ),
    }
    result.previous_metrics = prev

    # Check regressions
    cur_acc = current.get("top1_accuracy")
    prev_acc = prev.get("top1_accuracy")
    if cur_acc is not None and prev_acc is not None:
        drop = prev_acc - cur_acc
        if drop > max_accuracy_drop:
            result.regressions.append(
                f"Top-1 accuracy dropped {drop:.1%} (prev={prev_acc:.1%}, now={cur_acc:.1%})"
            )
            result.passed = False
        elif drop < -0.005:
            result.improvements.append(f"Top-1 accuracy improved by {-drop:.1%}")

    cur_recall = current.get("top3_recall")
    prev_recall = prev.get("top3_recall")
    if cur_recall is not None and prev_recall is not None:
        drop = prev_recall - cur_recall
        if drop > max_recall_drop:
            result.regressions.append(
                f"Top-3 recall dropped {drop:.1%} (prev={prev_recall:.1%}, now={cur_recall:.1%})"
            )
            result.passed = False
        elif drop < -0.005:
            result.improvements.append(f"Top-3 recall improved by {-drop:.1%}")

    cur_fp = current.get("auto_match_fp_rate")
    if cur_fp is None:
        cur_fp = current.get("auto_match_false_positive_rate")
    prev_fp = prev.get("auto_match_fp_rate")
    if cur_fp is not None and prev_fp is not None:
        increase = cur_fp - prev_fp
        if increase > max_fp_increase:
            result.regressions.append(
                f"FP rate increased {increase:.1%} (prev={prev_fp:.1%}, now={cur_fp:.1%})"
            )
            result.passed = False
        elif increase < -0.005:
            result.improvements.append(f"FP rate improved by {-increase:.1%}")

    if result.passed:
        logger.info("Quality gate PASSED: %s", result.improvements or "no regressions")
    else:
        logger.warning("Quality gate FAILED: %s", result.regressions)

    return result
