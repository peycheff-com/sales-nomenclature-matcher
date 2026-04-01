from __future__ import annotations

import re
import unicodedata

from matcher.normalization.pipeline import NormalizationContext


def unicode_cleanup(ctx: NormalizationContext) -> NormalizationContext:
    """NFKC normalization, lowercase, strip control chars, normalize whitespace."""
    text = ctx.text
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    # Remove control characters except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Normalize common punctuation
    text = text.replace("–", "-").replace("—", "-").replace("‐", "-")
    text = text.replace("«", '"').replace("»", '"')
    # Remove quotes
    text = text.replace('"', "").replace("'", "")
    ctx.text = text
    return ctx
