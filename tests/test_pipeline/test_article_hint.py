import re

from matcher.normalization.pipeline import run_pipeline
from matcher.pipeline.features import extract_features


def test_article_extracted_from_normalization():
    """Article codes in input should be extractable, not confused with brand."""
    ctx = run_pipeline("Насос Danfoss MSV-S 25 арт.96281375")
    features = extract_features(ctx)
    assert features.brand == "danfoss"
    assert features.article is not None
    assert "96281375" in features.article


def test_article_none_when_no_long_digits():
    """When there are no 6+ digit codes, article should be None."""
    ctx = run_pipeline("Труба ПВХ 50 мм")
    features = extract_features(ctx)
    assert features.article is None


def test_article_from_pure_digit_token():
    """A standalone 6+ digit token should be recognized as article."""
    ctx = run_pipeline("Кабель ВВГнг 3х2.5 12345678")
    features = extract_features(ctx)
    assert features.article is not None
    assert "12345678" in features.article


def test_article_not_set_for_short_numbers():
    """Numbers shorter than 6 digits are not articles."""
    ctx = run_pipeline("Болт М12 х 50 мм 1234")
    features = extract_features(ctx)
    assert features.article is None
