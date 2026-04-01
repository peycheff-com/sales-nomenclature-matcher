from __future__ import annotations

from matcher.pipeline.scoring import PairFeatures


def build_reasons(features: PairFeatures, short_circuit: str | None = None) -> list[str]:
    """Build human-readable explanation reasons from features."""
    reasons: list[str] = []

    if short_circuit == "supplier_exact":
        reasons.append("Найдено точное соответствие поставщика")
        return reasons

    if short_circuit == "article_brand_exact":
        reasons.append("Совпадает артикул и бренд")
        return reasons

    # Positive signals
    if features.brand_exact == 1.0:
        reasons.append("Совпадает бренд")
    elif features.brand_fuzzy > 0.7:
        reasons.append("Похожий бренд")

    if features.article_exact == 1.0:
        reasons.append("Совпадает артикул")

    if features.manufacturer_code_exact == 1.0:
        reasons.append("Совпадает код производителя")

    if features.number_signature_score >= 0.9:
        reasons.append("Совпадают ключевые числовые характеристики")
    elif features.number_signature_score >= 0.5:
        reasons.append("Частично совпадают числовые характеристики")

    if features.category_exact == 1.0:
        reasons.append("Совпадает категория")
    elif features.category_fuzzy > 0.5:
        reasons.append("Похожая категория")

    if features.unit_match_score == 1.0:
        reasons.append("Совпадает единица измерения")

    if features.packaging_match_score == 1.0:
        reasons.append("Совпадает фасовка")

    if features.alias_hit == 1.0:
        reasons.append("Найден через алиас")

    if features.rerank_score > 0.8:
        reasons.append("Высокая семантическая релевантность")
    elif features.lexical_score > 0.5:
        reasons.append("Высокое текстовое сходство")

    # Negative signals
    if features.critical_number_conflict:
        reasons.append("Конфликт по ключевым числовым характеристикам")

    if features.category_conflict:
        reasons.append("Конфликт по категории")

    if features.packaging_conflict:
        reasons.append("Конфликт по фасовке")

    if features.unit_conflict:
        reasons.append("Конфликт по единице измерения")

    if features.brand_conflict:
        reasons.append("Конфликт по бренду")

    return reasons
