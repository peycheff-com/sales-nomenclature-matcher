from matcher.pipeline.decision import decide
from matcher.pipeline.scoring import PairFeatures, ScoringResult


def test_decide_uses_custom_thresholds():
    features = PairFeatures(rerank_score=0.9, semantic_score=0.8, lexical_score=0.7)
    scoring = ScoringResult(final_score=0.91, features=features)

    # Default balanced (0.93) → review_needed
    result_default = decide(scoring, strict_mode=False)
    assert result_default.status == "review_needed"

    # Custom lower threshold → auto_match
    result_custom = decide(scoring, auto_threshold=0.90, review_threshold=0.75)
    assert result_custom.status == "auto_match"


def test_decide_custom_review_threshold():
    features = PairFeatures(rerank_score=0.5, semantic_score=0.5, lexical_score=0.5)
    scoring = ScoringResult(final_score=0.70, features=features)

    # Default balanced review_threshold=0.75 → no_match
    result_default = decide(scoring, strict_mode=False)
    assert result_default.status == "no_match"

    # Custom lower review threshold → review_needed
    result_custom = decide(scoring, auto_threshold=0.93, review_threshold=0.65)
    assert result_custom.status == "review_needed"


def test_decide_defaults_unchanged_without_custom():
    """Ensure default thresholds are preserved when no custom values given."""
    features = PairFeatures()
    scoring = ScoringResult(final_score=0.94, features=features)

    # Balanced mode default auto=0.93 → auto_match
    result = decide(scoring, strict_mode=False)
    assert result.status == "auto_match"

    # Strict mode default auto=0.96 → review_needed
    result_strict = decide(scoring, strict_mode=True)
    assert result_strict.status == "review_needed"


def test_decide_uses_supplier_and_category_threshold_fallbacks():
    features = PairFeatures()
    scoring = ScoringResult(final_score=0.86, features=features)

    supplier_result = decide(
        scoring,
        supplier_thresholds={"auto_threshold": 0.85, "review_threshold": 0.60},
        category_thresholds={"tools": {"auto_threshold": 0.99, "review_threshold": 0.98}},
        category="tools",
    )
    assert supplier_result.status == "auto_match"

    category_result = decide(
        scoring,
        category_thresholds={"tools": {"auto_threshold": 0.90, "review_threshold": 0.85}},
        category="tools",
    )
    assert category_result.status == "review_needed"


def test_decide_forbids_auto_match_when_scoring_sets_hard_gate():
    features = PairFeatures()
    scoring = ScoringResult(final_score=0.99, features=features, auto_match_forbidden=True)

    result = decide(scoring)

    assert result.status == "review_needed"
    assert result.auto_match_forbidden is True
