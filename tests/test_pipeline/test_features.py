from __future__ import annotations

from matcher.normalization.pipeline import NormalizationContext
from matcher.pipeline import features


def test_extract_numbers_from_text_handles_empty_and_invalid_tokens():
    assert features.extract_numbers_from_text("") == []
    assert features.extract_numbers_from_text("abc 12 3.5 7.") == [12.0, 3.5, 7.0]


def test_extract_numbers_from_text_skips_unparseable_regex_matches(monkeypatch):
    class _Match:
        def group(self):
            return "not-a-number"

    monkeypatch.setattr(features.re, "finditer", lambda *_args, **_kwargs: [_Match()])

    assert features.extract_numbers_from_text("12") == []


def test_extracted_features_to_dict_omits_raw_tokens():
    extracted = features.ExtractedFeatures(
        brand="bosch",
        article="123456",
        model="gbh",
        numbers=[2.0],
        dimensions=["10x20"],
        unit="pcs",
        packaging="box",
        material="steel",
        category_guess="tools",
        raw_tokens=["hidden"],
    )

    assert extracted.to_dict() == {
        "brand": "bosch",
        "article": "123456",
        "model": "gbh",
        "numbers": [2.0],
        "dimensions": ["10x20"],
        "unit": "pcs",
        "packaging": "box",
        "material": "steel",
        "category_guess": "tools",
    }


def test_extract_features_detects_packaging_and_explicit_article(monkeypatch):
    monkeypatch.setattr(features, "load_config", lambda: {"packaging_keywords": ["коробка"]})
    ctx = NormalizationContext(
        original="",
        text="",
        tokens=["bosch", "коробка", "арт.96281375", "12345678"],
        brand="bosch",
        numbers=[2.0],
        dimensions=["10x20"],
        unit="pcs",
    )

    extracted = features.extract_features(ctx)

    assert extracted.brand == "bosch"
    assert extracted.packaging == "коробка"
    assert extracted.article == "96281375"
    assert extracted.raw_tokens == ctx.tokens


def test_extract_features_uses_standalone_long_digit_article(monkeypatch):
    monkeypatch.setattr(features, "load_config", lambda: {"packaging_keywords": []})
    ctx = NormalizationContext(original="", text="", tokens=["abc", "12345678"])

    assert features.extract_features(ctx).article == "12345678"


def test_extract_features_without_article_or_packaging(monkeypatch):
    monkeypatch.setattr(features, "load_config", lambda: {"packaging_keywords": []})
    ctx = NormalizationContext(original="", text="", tokens=["abc", "123"])

    extracted = features.extract_features(ctx)

    assert extracted.article is None
    assert extracted.packaging is None
