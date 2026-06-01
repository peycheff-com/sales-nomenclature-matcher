"""Unit tests for scoring engine."""

from __future__ import annotations

from matcher.pipeline.decision import decide
from matcher.pipeline.explanations import build_reasons
from matcher.pipeline.scoring import (
    PairFeatures,
    ScoringResult,
    _compute_effective_weights,
    compute_attribute_overlap,
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
            candidate_has_identifiers=True,
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

    def test_effective_weights_return_base_weights_when_no_dead_metadata(self):
        f = PairFeatures(query_has_brand=True, candidate_has_brand=False)

        weights = _compute_effective_weights(f)

        assert weights["brand_exact"] > 0
        assert weights["brand_fuzzy"] > 0

    def test_effective_weights_redistribute_dead_brand_and_category(self):
        f = PairFeatures(lexical_score=0.5)

        weights = _compute_effective_weights(f)

        assert weights["brand_exact"] == 0.0
        assert weights["brand_fuzzy"] == 0.0
        assert weights["category_exact"] == 0.0
        assert weights["category_fuzzy"] == 0.0
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_score_candidate_applies_all_bonuses_and_generic_number_penalty(self):
        f = PairFeatures(
            article_exact=1.0,
            manufacturer_code_exact=1.0,
            brand_exact=0.0,
            brand_fuzzy=1.0,
            number_signature_score=0.95,
            alias_hit=1.0,
            critical_number_conflict=True,
            candidate_has_identifiers=False,
            lexical_score=1.0,
            semantic_score=1.0,
            rerank_score=1.0,
            packaging_match_score=1.0,
            unit_match_score=1.0,
            attribute_overlap_score=1.0,
            query_has_brand=True,
            candidate_has_brand=True,
        )

        result = score_candidate(f)

        assert round(result.bonus, 2) == 0.12
        assert result.penalty == -0.08
        assert not result.auto_match_forbidden

    def test_score_candidate_applies_packaging_unit_and_brand_penalties(self):
        f = PairFeatures(
            lexical_score=0.5,
            semantic_score=0.5,
            rerank_score=0.5,
            packaging_conflict=True,
            unit_conflict=True,
            brand_conflict=True,
            number_signature_score=0.7,
        )

        result = score_candidate(f)

        assert result.penalty == -0.30
        assert not result.auto_match_forbidden

    def test_category_conflict_allows_auto_when_rerank_is_very_high(self):
        f = PairFeatures(
            lexical_score=1.0,
            semantic_score=1.0,
            rerank_score=0.96,
            category_conflict=True,
        )

        result = score_candidate(f)

        assert not result.auto_match_forbidden


class TestComputePairFeatures:
    def test_attribute_overlap_handles_empty_and_partial_values(self):
        assert compute_attribute_overlap({}, {}) == 0.0
        assert compute_attribute_overlap({"brand": None}, {"brand": None}) == 0.0
        assert compute_attribute_overlap({"brand": "A"}, {"brand": None}) == 0.0
        assert (
            compute_attribute_overlap(
                {"numbers": [1, 2], "unit": "KG"},
                {"numbers": [2, 3], "unit": "kg"},
            )
            == 2 / 3
        )

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

    def test_article_manufacturer_brand_category_packaging_and_missing_unit_branches(self):
        f = compute_pair_features(
            query_brand="grund",
            query_numbers=[100.0],
            query_unit="kg",
            query_packaging="box",
            query_category="pump",
            candidate_brand="omega",
            candidate_article="A-1",
            candidate_manufacturer_code="Q-1",
            candidate_numbers=[110.0],
            candidate_unit=None,
            candidate_packaging="bo",
            candidate_category="valve",
            query_article="Q-1",
            lexical_score=2.0,
            semantic_score=-1.0,
            rerank_score=0.5,
            supplier_mapping_hit=True,
            alias_hit=True,
        )

        assert f.manufacturer_code_exact == 1.0
        assert f.article_exact == 0.0
        assert f.supplier_mapping_hit == 1.0
        assert f.alias_hit == 1.0
        assert f.lexical_score == 1.0
        assert f.semantic_score == 0.0
        assert f.brand_conflict
        assert f.category_conflict
        assert f.number_signature_score == 1.0
        assert f.unit_match_score == 0.5
        assert f.packaging_match_score == 0.5

    def test_missing_candidate_brand_is_not_a_conflict(self):
        f = compute_pair_features(
            query_brand="brand",
            query_numbers=[],
            query_unit=None,
            query_packaging=None,
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[],
            candidate_unit=None,
            candidate_packaging=None,
            candidate_category=None,
        )

        assert not f.brand_conflict
        assert f.query_has_brand
        assert not f.candidate_has_brand

    def test_article_exact_and_candidate_only_unit_and_packaging_conflict(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[],
            query_unit=None,
            query_packaging="bag",
            query_category="pump",
            candidate_brand="Brand",
            candidate_article="A-1",
            candidate_manufacturer_code=None,
            candidate_numbers=[],
            candidate_unit="pcs",
            candidate_packaging="box",
            candidate_category="pump",
            query_article="a-1",
        )

        assert f.article_exact == 1.0
        assert f.candidate_has_identifiers
        assert f.candidate_has_brand
        assert f.category_exact == 1.0
        assert f.unit_match_score == 0.5
        assert f.packaging_conflict

    def test_packaging_exact_match_sets_full_score(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[],
            query_unit=None,
            query_packaging="box",
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[],
            candidate_unit=None,
            candidate_packaging="BOX",
            candidate_category=None,
        )

        assert f.packaging_match_score == 1.0

    def test_query_number_without_candidate_numbers_sets_zero_score(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[10.0],
            query_unit=None,
            query_packaging=None,
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[],
            candidate_unit=None,
            candidate_packaging=None,
            candidate_category=None,
        )

        assert f.number_signature_score == 0.0
        assert not f.critical_number_conflict

    def test_fuzzy_number_matching_skips_already_matched_candidates(self):
        f = compute_pair_features(
            query_brand=None,
            query_numbers=[10.0, 10.4],
            query_unit=None,
            query_packaging=None,
            query_category=None,
            candidate_brand=None,
            candidate_article=None,
            candidate_manufacturer_code=None,
            candidate_numbers=[10.0],
            candidate_unit=None,
            candidate_packaging=None,
            candidate_category=None,
        )

        assert f.number_signature_score == 0.5


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
