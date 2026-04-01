from __future__ import annotations

from dataclasses import dataclass

from matcher.pipeline.scoring import ScoringResult


@dataclass
class MatchDecision:
    status: str  # auto_match | review_needed | no_match
    confidence: float
    auto_match_forbidden: bool = False


def decide(
    scoring: ScoringResult,
    strict_mode: bool = False,
    auto_threshold: float | None = None,
    review_threshold: float | None = None,
    supplier_thresholds: dict | None = None,
    category_thresholds: dict | None = None,
    category: str | None = None,
) -> MatchDecision:
    """Apply decision thresholds to a scoring result.

    Threshold resolution order:
      1. Explicit auto_threshold/review_threshold parameters (highest priority)
      2. supplier_thresholds dict (if provided)
      3. category_thresholds[category] dict (if category provided)
      4. Global defaults (strict_mode-dependent)
    """
    # Resolve thresholds with fallback chain:
    # explicit params > supplier > category > global
    resolved_auto = auto_threshold
    resolved_review = review_threshold

    if resolved_auto is None and supplier_thresholds:
        resolved_auto = supplier_thresholds.get("auto_threshold")
        resolved_review = resolved_review or supplier_thresholds.get("review_threshold")

    if resolved_auto is None and category_thresholds and category:
        cat_t = category_thresholds.get(category, {})
        resolved_auto = cat_t.get("auto_threshold")
        resolved_review = resolved_review or cat_t.get("review_threshold")

    if resolved_auto is None:
        resolved_auto = 0.96 if strict_mode else 0.93
    if resolved_review is None:
        resolved_review = 0.80 if strict_mode else 0.75

    score = scoring.final_score
    forbidden = scoring.auto_match_forbidden

    if score >= resolved_auto and not forbidden:
        status = "auto_match"
    elif score >= resolved_review:
        status = "review_needed"
    else:
        status = "no_match"

    return MatchDecision(
        status=status,
        confidence=score,
        auto_match_forbidden=forbidden,
    )
