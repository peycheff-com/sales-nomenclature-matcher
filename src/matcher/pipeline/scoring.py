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
    # Metadata richness
    candidate_has_identifiers: bool = False


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
    f.candidate_has_identifiers = bool(candidate_article or candidate_brand)

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
            f.unit_match_score = 0.0
    elif qu and not cu:
        # Query has unit but candidate doesn't — not a conflict, just missing data
        f.unit_match_score = 0.5
    elif cu and not qu:
        f.unit_match_score = 0.5
    else:
        # Neither has unit
        f.unit_match_score = 0.5

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
            f.packaging_match_score = 0.0
    else:
        # One or both sides missing — not a conflict
        f.packaging_match_score = 0.5

    return f


def _compute_effective_weights(features: PairFeatures) -> dict[str, float]:
    """Dynamically redistribute weights when metadata features are inapplicable.

    When both sides of a comparison lack data (e.g., no brand on query AND no brand
    on candidate), that feature cannot contribute signal. Its weight is redistributed
    proportionally to features that DO have signal, so the total always sums to 1.0.
    """
    weights = dict(WEIGHTS)

    # Detect inapplicable features (both sides missing → no signal possible)
    dead_keys: list[str] = []

    # Brand: inapplicable when BOTH query and candidate have no brand
    if features.brand_exact == 0.0 and features.brand_fuzzy == 0.0 and not features.brand_conflict:
        # Could be a match with no brand data on either side
        dead_keys.extend(["brand_exact", "brand_fuzzy"])

    # Category: inapplicable when both sides have no category
    if (
        features.category_exact == 0.0
        and features.category_fuzzy == 0.0
        and not features.category_conflict
    ):
        dead_keys.extend(["category_exact", "category_fuzzy"])

    if not dead_keys:
        return weights

    # Redistribute dead weight proportionally to live features
    dead_weight = sum(weights[k] for k in dead_keys)
    live_keys = [k for k in weights if k not in dead_keys]
    live_weight = sum(weights[k] for k in live_keys)

    if live_weight > 0:
        scale = (live_weight + dead_weight) / live_weight
        for k in live_keys:
            weights[k] *= scale
    for k in dead_keys:
        weights[k] = 0.0

    return weights


def score_candidate(features: PairFeatures) -> ScoringResult:
    """Apply Scoring Formula v2 to computed features.

    v2 changes from v1:
    - Dynamic weight redistribution for sparse catalogs (missing brand/category)
    - Eliminates dead-weight features that cap the score ceiling
    """
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

    # Compute effective weights (redistributes dead metadata weight)
    w = _compute_effective_weights(features)

    # Base score
    result.base_score = (
        w["brand_exact"] * features.brand_exact
        + w["brand_fuzzy"] * features.brand_fuzzy
        + w["category_exact"] * features.category_exact
        + w["category_fuzzy"] * features.category_fuzzy
        + w["lexical_score"] * features.lexical_score
        + w["semantic_score"] * features.semantic_score
        + w["rerank_score"] * features.rerank_score
        + w["number_signature_score"] * features.number_signature_score
        + w["packaging_match_score"] * features.packaging_match_score
        + w["unit_match_score"] * features.unit_match_score
        + w["attribute_overlap_score"] * features.attribute_overlap_score
        + w["alias_hit"] * features.alias_hit
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
        if features.candidate_has_identifiers:
            penalty -= 0.18  # Specific product, wrong numbers
        else:
            penalty -= 0.08  # Generic product, numbers just differentiate variants
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
        and features.candidate_has_identifiers
    ):
        result.auto_match_forbidden = True
    if features.category_conflict and features.rerank_score < 0.95:
        result.auto_match_forbidden = True
    if features.brand_conflict and features.number_signature_score < 0.6:
        result.auto_match_forbidden = True

    return result
