from __future__ import annotations

import re
from dataclasses import dataclass, field

from matcher.normalization.pipeline import NormalizationContext, load_config

# Matches tokens that are pure 6+ digit codes (likely article/part numbers)
_ARTICLE_DIGIT_RE = re.compile(r"^\d{6,}$")
# Matches tokens like "арт.96281375" or "арт96281375"
_ARTICLE_PREFIX_RE = re.compile(r"^(?:арт\.?|art\.?)(\d{6,})$", re.IGNORECASE)


def extract_numbers_from_text(text: str) -> list[float]:
    """Extract numbers from text for scoring and comparison."""
    if not text:
        return []
    nums = []
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        try:
            nums.append(float(m.group()))
        except ValueError:
            pass
    return nums


@dataclass
class ExtractedFeatures:
    brand: str | None = None
    article: str | None = None
    model: str | None = None
    numbers: list[float] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    unit: str | None = None
    packaging: str | None = None
    material: str | None = None
    category_guess: str | None = None
    raw_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "article": self.article,
            "model": self.model,
            "numbers": self.numbers,
            "dimensions": self.dimensions,
            "unit": self.unit,
            "packaging": self.packaging,
            "material": self.material,
            "category_guess": self.category_guess,
        }


def extract_features(ctx: NormalizationContext) -> ExtractedFeatures:
    """Extract structured features from normalization context."""
    config = load_config()
    packaging_kw = set(w.lower() for w in config.get("packaging_keywords", []))

    features = ExtractedFeatures(
        brand=ctx.brand,
        numbers=ctx.numbers,
        dimensions=ctx.dimensions,
        unit=ctx.unit,
        raw_tokens=ctx.tokens,
    )

    # Detect packaging from tokens
    for token in ctx.tokens:
        if token.lower() in packaging_kw:
            features.packaging = token.lower()
            break

    # Extract article code from tokens
    # Priority 1: tokens with explicit article prefix (e.g. "арт.96281375")
    # Priority 2: standalone 6+ digit tokens (e.g. "12345678")
    article_code: str | None = None
    for token in ctx.tokens:
        m = _ARTICLE_PREFIX_RE.match(token)
        if m:
            article_code = m.group(1)
            break  # Explicit prefix is highest priority

    if article_code is None:
        for token in ctx.tokens:
            if _ARTICLE_DIGIT_RE.match(token):
                article_code = token
                break

    features.article = article_code

    return features
