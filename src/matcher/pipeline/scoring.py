from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz


@dataclass
class PairFeatures:
    """Features for a (query, candidate) pair."""

    # Binary
    article_exact: float = 0.0
    manufacturer_code_exact: float = 0.0
    supplier_mapping_hit: float = 0.0
    brand_exact: float = 0.0
    category_exact: float = 0.0
    alias_hit: float = 0.0
    # Continuous
    brand_fuzzy: float = 0.0
    category_fuzzy: float = 0.0
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rerank_score: float = 0.0
    number_signature_score: float = 0.0
    packaging_match_score: float = 0.0
    unit_match_score: float = 0.0
    attribute_overlap_score: float = 0.0
    # Conflict flags
    critical_number_conflict: bool = False
    category_conflict: bool = False
    packaging_conflict: bool = False
    unit_conflict: bool = False
    brand_conflict: bool = False


@dataclass
class ScoringResult:
    """Result of the scoring formula."""

    base_score: float = 0.0
    bonus: float = 0.0
    penalty: float = 0.0
    final_score: float = 0.0
    auto_match_forbidden: bool = False
    short_circuit: str | None = None
    features: PairFeatures = field(default_factory=PairFeatures)


# Base score weights (sum = 1.00)
WEIGHTS = {
    "brand_exact": 0.08,
    "brand_fuzzy": 0.04,
    "category_exact": 0.06,
    "category_fuzzy": 0.03,
    "lexical_score": 0.12,
    "semantic_score": 0.18,
    "rerank_score": 0.26,
    "number_signature_score": 0.14,
    "packaging_match_score": 0.03,
    "unit_match_score": 0.02,
    "attribute_overlap_score": 0.03,
    "alias_hit": 0.01,
}


def compute_attribute_overlap(query_attrs: dict, candidate_attrs: dict) -> float:
    """Compute Jaccard-like overlap of non-None extracted attributes."""
    keys = set(query_attrs.keys()) | set(candidate_attrs.keys())
    comparable = []
    for k in keys:
        qv = query_attrs.get(k)
        cv = candidate_attrs.get(k)
        if qv is None and cv is None:
            continue
        comparable.append((qv, cv))

    if not comparable:
        return 0.0

    matches = 0
    for qv, cv in comparable:
        if qv is None or cv is None:
            continue
        if isinstance(qv, list) and isinstance(cv, list):
            qset, cset = set(str(x) for x in qv), set(str(x) for x in cv)
            if qset and cset:
                matches += len(qset & cset) / len(qset | cset)
        elif str(qv).lower().strip() == str(cv).lower().strip():
            matches += 1

    return matches / len(comparable)


def compute_pair_features(
    query_brand: str | None,
    query_numbers: list[float],
    query_unit: str | None,
    query_packaging: str | None,
    query_category: str | None,
    candidate_brand: str | None,
    candidate_article: str | None,
    candidate_manufacturer_code: str | None,
    candidate_numbers: list[float],
    candidate_unit: str | None,
    candidate_packaging: str | None,
    candidate_category: str | None,
    lexical_score: float = 0.0,
    semantic_score: float = 0.0,
    rerank_score: float = 0.0,
    query_article: str | None = None,
    supplier_mapping_hit: bool = False,
    alias_hit: bool = False,
) -> PairFeatures:
    """Compute the 15 features for a query-candidate pair."""
    f = PairFeatures()

    f.lexical_score = min(1.0, max(0.0, lexical_score))
    f.semantic_score = min(1.0, max(0.0, semantic_score))
    f.rerank_score = min(1.0, max(0.0, rerank_score))
    f.supplier_mapping_hit = 1.0 if supplier_mapping_hit else 0.0
    f.alias_hit = 1.0 if alias_hit else 0.0

    # Article exact match
    if query_article and candidate_article:
        if query_article.lower().strip() == candidate_article.lower().strip():
            f.article_exact = 1.0

    # Manufacturer code exact match
    if query_article and candidate_manufacturer_code:
        if query_article.lower().strip() == candidate_manufacturer_code.lower().strip():
            f.manufacturer_code_exact = 1.0

    # Brand matching
    qb = (query_brand or "").lower().strip()
    cb = (candidate_brand or "").lower().strip()
    if qb and cb:
        if qb == cb:
            f.brand_exact = 1.0
            f.brand_fuzzy = 1.0
        else:
            ratio = fuzz.ratio(qb, cb) / 100.0
            f.brand_fuzzy = ratio
            if ratio < 0.4:
                f.brand_conflict = True
    elif qb and not cb:
        pass  # No conflict, candidate just has no brand
    elif cb and not qb:
        pass

    # Category matching
    qc = (query_category or "").lower().strip()
    cc = (candidate_category or "").lower().strip()
    if qc and cc:
        if qc == cc:
            f.category_exact = 1.0
            f.category_fuzzy = 1.0
        else:
            ratio = fuzz.ratio(qc, cc) / 100.0
            f.category_fuzzy = ratio
            if ratio < 0.3:
                f.category_conflict = True

    # Number signature matching (Jaccard on critical numbers)
    qn = set(query_numbers)
    cn = set(candidate_numbers)
    if qn and cn:
        intersection = qn & cn
        union = qn | cn
        f.number_signature_score = len(intersection) / len(union) if union else 0.0
        # Critical number conflict: query has numbers but none match
        if len(intersection) == 0 and len(qn) > 0:
            f.critical_number_conflict = True
    elif qn and not cn:
        # Query has numbers but candidate doesn't — mild concern, not conflict
        f.number_signature_score = 0.0

    # Unit matching
    qu = (query_unit or "").lower().strip()
    cu = (candidate_unit or "").lower().strip()
    if qu and cu:
        if qu == cu:
            f.unit_match_score = 1.0
        else:
            f.unit_conflict = True
    elif not qu or not cu:
        f.unit_match_score = 0.5  # Unknown, give partial credit

    # Packaging matching
    qp = (query_packaging or "").lower().strip()
    cp = (candidate_packaging or "").lower().strip()
    if qp and cp:
        if qp == cp:
            f.packaging_match_score = 1.0
        elif fuzz.ratio(qp, cp) > 60:
            f.packaging_match_score = 0.5
        else:
            f.packaging_conflict = True
    elif not qp or not cp:
        f.packaging_match_score = 0.5  # Unknown

    return f


def score_candidate(features: PairFeatures) -> ScoringResult:
    """Apply Scoring Formula v1 to computed features."""
    result = ScoringResult(features=features)

    # Short-circuit: supplier exact mapping
    if features.supplier_mapping_hit == 1.0:
        result.final_score = 0.995
        result.short_circuit = "supplier_exact"
        return result

    # Short-circuit: article + brand exact
    if features.article_exact == 1.0 and features.brand_exact == 1.0:
        result.final_score = 0.985
        result.short_circuit = "article_brand_exact"
        return result

    # Base score
    result.base_score = (
        WEIGHTS["brand_exact"] * features.brand_exact
        + WEIGHTS["brand_fuzzy"] * features.brand_fuzzy
        + WEIGHTS["category_exact"] * features.category_exact
        + WEIGHTS["category_fuzzy"] * features.category_fuzzy
        + WEIGHTS["lexical_score"] * features.lexical_score
        + WEIGHTS["semantic_score"] * features.semantic_score
        + WEIGHTS["rerank_score"] * features.rerank_score
        + WEIGHTS["number_signature_score"] * features.number_signature_score
        + WEIGHTS["packaging_match_score"] * features.packaging_match_score
        + WEIGHTS["unit_match_score"] * features.unit_match_score
        + WEIGHTS["attribute_overlap_score"] * features.attribute_overlap_score
        + WEIGHTS["alias_hit"] * features.alias_hit
    )

    # Bonuses
    bonus = 0.0
    if features.article_exact == 1.0:
        bonus += 0.05
    if features.manufacturer_code_exact == 1.0:
        bonus += 0.05
    if features.brand_exact == 1.0 and features.number_signature_score >= 0.9:
        bonus += 0.03
    if features.alias_hit == 1.0:
        bonus += 0.02
    result.bonus = bonus

    # Penalties
    penalty = 0.0
    if features.critical_number_conflict:
        penalty -= 0.18
    if features.category_conflict:
        penalty -= 0.15
    if features.packaging_conflict:
        penalty -= 0.12
    if features.unit_conflict:
        penalty -= 0.10
    if (
        features.brand_conflict
        and features.article_exact == 0.0
        and features.manufacturer_code_exact == 0.0
    ):
        penalty -= 0.08
    result.penalty = penalty

    # Final score
    raw = result.base_score + result.bonus + result.penalty
    result.final_score = min(1.0, max(0.0, raw))

    # Hard gates
    if (
        features.critical_number_conflict
        and features.article_exact == 0.0
        and features.manufacturer_code_exact == 0.0
    ):
        result.auto_match_forbidden = True
    if features.category_conflict and features.rerank_score < 0.95:
        result.auto_match_forbidden = True
    if features.brand_conflict and features.number_signature_score < 0.6:
        result.auto_match_forbidden = True

    return result
