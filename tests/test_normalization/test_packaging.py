"""Tests for packaging normalization."""

from matcher.normalization.packaging import normalize_packaging
from matcher.normalization.pipeline import NormalizationContext


def test_alias_expansion():
    ctx = NormalizationContext(original="клей 25кг упак.")
    result = normalize_packaging(ctx)
    assert "упаковка" in result.text


def test_keyword_detection():
    ctx = NormalizationContext(original="клей 25кг упаковка")
    result = normalize_packaging(ctx)
    assert result.packaging == "упаковка"


def test_keyword_rulon():
    ctx = NormalizationContext(original="рулон обоев")
    result = normalize_packaging(ctx)
    assert result.packaging == "рулон"


def test_keyword_meshok():
    ctx = NormalizationContext(original="мешок цемента")
    result = normalize_packaging(ctx)
    assert result.packaging == "мешок"


def test_no_packaging():
    ctx = NormalizationContext(original="труба пп 32 мм")
    result = normalize_packaging(ctx)
    assert result.packaging is None


def test_word_boundary_banan():
    """'банан' should NOT trigger 'бан' alias expansion."""
    ctx = NormalizationContext(original="банан")
    result = normalize_packaging(ctx)
    # "бан" alias expands to "банка" but only on word boundary
    assert "банка" not in result.text
