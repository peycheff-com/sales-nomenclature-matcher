from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from matcher.normalization.abbreviations import expand_abbreviations
from matcher.normalization.cyrillic_latin import _normalize_token
from matcher.normalization.db_synonyms import apply_db_synonyms
from matcher.normalization.number_extractor import extract_numbers
from matcher.normalization.pipeline import NormalizationContext
from matcher.normalization.unit_normalizer import normalize_units


def test_expand_abbreviations_returns_original_when_config_has_no_map(monkeypatch):
    ctx = NormalizationContext(original="без сокращений")
    monkeypatch.setattr("matcher.normalization.abbreviations.load_config", lambda: {})

    assert expand_abbreviations(ctx) is ctx
    assert ctx.text == "без сокращений"


def test_cyrillic_latin_normalize_converts_majority_latin_confusables_to_latin():
    assert _normalize_token("abcр") == "abcp"


def test_extract_numbers_ignores_unparseable_regex_match(monkeypatch):
    ctx = NormalizationContext(original="value 10")

    class Match:
        def group(self):
            return "not-a-number"

    monkeypatch.setattr(
        "matcher.normalization.number_extractor.load_config",
        lambda: {"dimension_patterns": []},
    )
    monkeypatch.setattr(
        "matcher.normalization.number_extractor.re.finditer",
        lambda *_args, **_kwargs: [Match()],
    )

    result = extract_numbers(ctx)

    assert result.numbers == []


def test_normalize_units_leaves_unit_none_when_only_dimensional_units_are_seen(monkeypatch):
    ctx = NormalizationContext(original="лист 10 мм")
    monkeypatch.setattr(
        "matcher.normalization.unit_normalizer.load_config",
        lambda: {"unit_aliases": {"мм": "mm"}},
    )

    result = normalize_units(ctx)

    assert result.text == "лист 10 mm"
    assert result.unit is None


def test_normalize_units_detects_standalone_unit_words(monkeypatch):
    ctx = NormalizationContext(original="кабель бухта")
    monkeypatch.setattr(
        "matcher.normalization.unit_normalizer.load_config",
        lambda: {"unit_aliases": {"бухта": "roll"}},
    )

    result = normalize_units(ctx)

    assert result.text == "кабель roll"
    assert result.unit == "roll"


@pytest.mark.asyncio
async def test_apply_db_synonyms_loads_map_from_repo():
    ctx = NormalizationContext(original="насос старое название")
    repo = AsyncMock()
    repo.build_synonym_map = AsyncMock(return_value={"старое название": "новое название"})

    result = await apply_db_synonyms(ctx, repo, supplier_id="s1")

    repo.build_synonym_map.assert_awaited_once_with(supplier_id="s1")
    assert result.text == "насос новое название"
    assert result.extras["db_synonyms_applied"] == ["старое название->новое название"]
