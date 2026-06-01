from __future__ import annotations

from matcher.pipeline.explanations import build_reasons
from matcher.pipeline.scoring import PairFeatures


def test_build_reasons_short_circuit_supplier_exact():
    assert build_reasons(PairFeatures(), short_circuit="supplier_exact") == [
        "Найдено точное соответствие поставщика"
    ]


def test_build_reasons_short_circuit_article_brand_exact():
    assert build_reasons(PairFeatures(), short_circuit="article_brand_exact") == [
        "Совпадает артикул и бренд"
    ]


def test_build_reasons_positive_and_negative_signals():
    features = PairFeatures(
        brand_exact=1.0,
        article_exact=1.0,
        manufacturer_code_exact=1.0,
        number_signature_score=0.95,
        category_exact=1.0,
        unit_match_score=1.0,
        packaging_match_score=1.0,
        alias_hit=1.0,
        rerank_score=0.9,
        critical_number_conflict=True,
        category_conflict=True,
        packaging_conflict=True,
        unit_conflict=True,
        brand_conflict=True,
    )

    reasons = build_reasons(features)

    assert "Совпадает бренд" in reasons
    assert "Совпадает артикул" in reasons
    assert "Совпадает код производителя" in reasons
    assert "Совпадают ключевые числовые характеристики" in reasons
    assert "Совпадает категория" in reasons
    assert "Совпадает единица измерения" in reasons
    assert "Совпадает фасовка" in reasons
    assert "Найден через алиас" in reasons
    assert "Высокая семантическая релевантность" in reasons
    assert "Конфликт по ключевым числовым характеристикам" in reasons
    assert "Конфликт по категории" in reasons
    assert "Конфликт по фасовке" in reasons
    assert "Конфликт по единице измерения" in reasons
    assert "Конфликт по бренду" in reasons


def test_build_reasons_fuzzy_and_partial_signals():
    features = PairFeatures(
        brand_fuzzy=0.8,
        number_signature_score=0.5,
        category_fuzzy=0.6,
        lexical_score=0.7,
    )

    assert build_reasons(features) == [
        "Похожий бренд",
        "Частично совпадают числовые характеристики",
        "Похожая категория",
        "Высокое текстовое сходство",
    ]
