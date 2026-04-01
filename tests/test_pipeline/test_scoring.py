"""Unit tests for scoring engine."""

from __future__ import annotations

from matcher.pipeline.decision import decide
from matcher.pipeline.explanations import build_reasons
from matcher.pipeline.scoring import (
    PairFeatures,
    ScoringResult,
    compute_pair_features,
    score_candidate,
)


class TestScoringFormula:
    def test_supplier_exact_short_circuit(self):
        f = PairFeatures(supplier_mapping_hit=1.0)
        result = score_candidate(f)
        assert result.final_score == 0.995
        assert result.short_circuit == "supplier_exact"

    def test_article_brand_short_circuit(self):
        f = PairFeatures(article_exact=1.0, brand_exact=1.0)
        result = score_candidate(f)
        assert result.final_score == 0.985
        assert result.short_circuit == "article_brand_exact"

    def test_base_score_weights_sum_to_one(self):
        from matcher.pipeline.scoring import WEIGHTS

        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_perfect_match_high_score(self):
        f = PairFeatures(
            brand_exact=1.0,
            brand_fuzzy=1.0,
            category_exact=1.0,
            category_fuzzy=1.0,
            lexical_score=0.9,
            semantic_score=0.9,
            rerank_score=0.9,
            number_signature_score=1.0,
            packaging_match_score=1.0,
            unit_match_score=1.0,
            attribute_overlap_score=0.8,
            alias_hit=0.0,
        )
        result = score_candidate(f)
        assert result.final_score > 0.9
        assert result.bonus > 0  # brand + numbers bonus

    def test_number_conflict_penalty(self):
        f = PairFeatures(
            lexical_score=0.8,
            semantic_score=0.8,
            rerank_score=0.8,
            critical_number_conflict=True,
        )
        result = score_candidate(f)
        assert result.penalty < 0
        assert result.auto_match_forbidden

    def test_category_conflict_blocks_auto_match(self):
        f = PairFeatures(
            lexical_score=0.9,
            semantic_score=0.9,
            rerank_score=0.9,
            category_conflict=True,
        )
        result = score_candidate(f)
        assert result.auto_match_forbidden

    def test_brand_conflict_with_low_numbers(self):
        f = PairFeatures(
            lexical_score=0.7,
            semantic_score=0.7,
            rerank_score=0.7,
            brand_conflict=True,
            number_signature_score=0.3,
        )
        result = score_candidate(f)
        assert result.auto_match_forbidden

    def test_score_clamped_to_0_1(self):
        f = PairFeatures(
            critical_number_conflict=True,
            category_conflict=True,
            packaging_conflict=True,
            unit_conflict=True,
            brand_conflict=True,
        )
        result = score_candidate(f)
        assert result.final_score >= 0.0
        assert result.final_score <= 1.0


class TestComputePairFeatures:
    def test_brand_exact_match(self):
        f = compute_pair_features(
            query_brand="grundfos",
            query_numbers=[25, 40],
            query_unit=None,
            query_packaging=None,
            query_category=None,
            candidate_brand="grundfos",
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[25, 40, 180],
            candidate_unit=None,
            candidate_packaging=None,
            candidate_category=None,
        )
        assert f.brand_exact == 1.0
        assert f.number_signature_score > 0.5  # 2/3 overlap

    def test_number_conflict_detected(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[32],
            query_unit="mm",
            query_packaging=None,
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[50],
            candidate_unit="mm",
            candidate_packaging=None,
            candidate_category=None,
        )
        assert f.critical_number_conflict

    def test_unit_conflict_detected(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[],
            query_unit="mm",
            query_packaging=None,
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[],
            candidate_unit="m",
            candidate_packaging=None,
            candidate_category=None,
        )
        assert f.unit_conflict


class TestDecision:
    def test_auto_match(self):
        scoring = ScoringResult(final_score=0.95)
        d = decide(scoring)
        assert d.status == "auto_match"

    def test_review_needed(self):
        scoring = ScoringResult(final_score=0.85)
        d = decide(scoring)
        assert d.status == "review_needed"

    def test_no_match(self):
        scoring = ScoringResult(final_score=0.5)
        d = decide(scoring)
        assert d.status == "no_match"

    def test_forbidden_auto_match(self):
        scoring = ScoringResult(final_score=0.95, auto_match_forbidden=True)
        d = decide(scoring)
        assert d.status == "review_needed"

    def test_strict_mode_higher_threshold(self):
        scoring = ScoringResult(final_score=0.94)
        d = decide(scoring, strict_mode=True)
        assert d.status == "review_needed"  # 0.94 < 0.96 in strict


class TestExplanations:
    def test_supplier_short_circuit(self):
        f = PairFeatures()
        reasons = build_reasons(f, short_circuit="supplier_exact")
        assert len(reasons) == 1
        assert "поставщика" in reasons[0]

    def test_brand_match_reason(self):
        f = PairFeatures(brand_exact=1.0)
        reasons = build_reasons(f)
        assert any("бренд" in r.lower() for r in reasons)

    def test_number_conflict_reason(self):
        f = PairFeatures(critical_number_conflict=True)
        reasons = build_reasons(f)
        assert any("конфликт" in r.lower() for r in reasons)

    def test_multiple_reasons(self):
        f = PairFeatures(
            brand_exact=1.0,
            number_signature_score=0.95,
            category_exact=1.0,
            unit_match_score=1.0,
        )
        reasons = build_reasons(f)
        assert len(reasons) >= 3
