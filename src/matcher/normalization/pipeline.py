from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml


@dataclass
class NormalizationContext:
    """Accumulated state through the normalization pipeline."""

    original: str
    text: str = ""
    tokens: list[str] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    brand: str | None = None
    unit: str | None = None
    packaging: str | None = None
    category_guess: str | None = None
    extras: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.text:
            self.text = self.original


class Transform(Protocol):
    def __call__(self, ctx: NormalizationContext) -> NormalizationContext: ...


_config_cache: dict | None = None


def load_config(path: str | Path | None = None) -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if path is None:
        path = Path(__file__).resolve().parents[3] / "configs" / "normalization.yaml"
    with open(path) as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def run_pipeline(text: str, transforms: list[Transform] | None = None) -> NormalizationContext:
    """Run normalization pipeline on input text."""
    if transforms is None:
        transforms = default_transforms()
    ctx = NormalizationContext(original=text)
    for transform in transforms:
        ctx = transform(ctx)
    return ctx


def default_transforms() -> list[Transform]:
    from matcher.normalization.brand_detector import detect_brand
    from matcher.normalization.cyrillic_latin import cyrillic_latin_normalize
    from matcher.normalization.number_extractor import extract_numbers
    from matcher.normalization.stopwords import remove_stopwords
    from matcher.normalization.tokenizer import tokenize
    from matcher.normalization.unicode_cleanup import unicode_cleanup
    from matcher.normalization.unit_normalizer import normalize_units

    return [
        unicode_cleanup,
        cyrillic_latin_normalize,
        extract_numbers,
        normalize_units,
        detect_brand,
        remove_stopwords,
        tokenize,
    ]
