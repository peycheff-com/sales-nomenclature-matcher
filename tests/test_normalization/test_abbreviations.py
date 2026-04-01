"""Tests for abbreviation expansion."""

import pytest

from matcher.normalization.abbreviations import expand_abbreviations
from matcher.normalization.pipeline import NormalizationContext


@pytest.mark.parametrize(
    "input_text,expected_substring",
    [
        ("труба пвх 110", "поливинилхлорид"),
        ("плита осб 12мм", "ориентированно стружечная плита"),
        ("лист гкл 12.5", "гипсокартон"),
        ("нерж сталь", "нержавеющая"),
        ("провод ввг 3x2.5", "ввг"),
    ],
)
def test_known_abbreviations_expand(input_text, expected_substring):
    ctx = NormalizationContext(original=input_text)
    result = expand_abbreviations(ctx)
    assert expected_substring in result.text.lower()


def test_word_boundary_prevents_partial_match():
    ctx = NormalizationContext(original="осбенный")
    result = expand_abbreviations(ctx)
    assert "ориентированно" not in result.text


def test_empty_text_returns_unchanged():
    ctx = NormalizationContext(original="")
    result = expand_abbreviations(ctx)
    assert result.text == ""
