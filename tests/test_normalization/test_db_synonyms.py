"""Tests for DB-driven synonym application."""

from unittest.mock import AsyncMock

from matcher.normalization.db_synonyms import apply_db_synonyms
from matcher.normalization.pipeline import NormalizationContext


class TestApplyDbSynonyms:
    async def test_basic_replacement(self):
        ctx = NormalizationContext(original="нерж труба 25")
        synonym_map = {"нерж": "нержавеющая сталь"}
        repo = AsyncMock()
        result = await apply_db_synonyms(ctx, repo, synonym_map=synonym_map)
        assert "нержавеющая сталь" in result.text

    async def test_empty_map_noop(self):
        ctx = NormalizationContext(original="труба стальная 25")
        repo = AsyncMock()
        result = await apply_db_synonyms(ctx, repo, synonym_map={})
        assert result.text == "труба стальная 25"

    async def test_synonym_map_param_skips_db(self):
        ctx = NormalizationContext(original="нерж труба")
        repo = AsyncMock()
        synonym_map = {"нерж": "нержавеющая сталь"}
        await apply_db_synonyms(ctx, repo, synonym_map=synonym_map)
        repo.build_synonym_map.assert_not_called()

    async def test_applied_tracked_in_extras(self):
        ctx = NormalizationContext(original="нерж труба")
        synonym_map = {"нерж": "нержавеющая сталь"}
        repo = AsyncMock()
        result = await apply_db_synonyms(ctx, repo, synonym_map=synonym_map)
        assert "db_synonyms_applied" in result.extras
        assert any("нерж" in entry for entry in result.extras["db_synonyms_applied"])

    async def test_word_boundary_prevents_substring(self):
        """Synonym 'ст' should NOT match inside 'стойка'."""
        ctx = NormalizationContext(original="стойка металлическая")
        synonym_map = {"ст": "сталь"}
        repo = AsyncMock()
        result = await apply_db_synonyms(ctx, repo, synonym_map=synonym_map)
        assert result.text == "стойка металлическая"

    async def test_longest_match_first(self):
        ctx = NormalizationContext(original="труба стальная 25")
        synonym_map = {"труба стальная": "x", "труба": "y"}
        repo = AsyncMock()
        result = await apply_db_synonyms(ctx, repo, synonym_map=synonym_map)
        assert "x" in result.text
        # "труба" alone should NOT have been replaced since "труба стальная" consumed it
        assert "y" not in result.text
