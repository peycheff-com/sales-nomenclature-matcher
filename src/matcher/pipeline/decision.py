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
) -> MatchDecision:
    """Apply decision thresholds to a scoring result."""
    if auto_threshold is None:
        auto_threshold = 0.96 if strict_mode else 0.93
    if review_threshold is None:
        review_threshold = 0.80 if strict_mode else 0.75

    score = scoring.final_score
    forbidden = scoring.auto_match_forbidden

    if score >= auto_threshold and not forbidden:
        status = "auto_match"
    elif score >= review_threshold:
        status = "review_needed"
    else:
        status = "no_match"

    return MatchDecision(
        status=status,
        confidence=score,
        auto_match_forbidden=forbidden,
    )
