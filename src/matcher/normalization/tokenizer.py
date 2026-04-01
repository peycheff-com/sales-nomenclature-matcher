from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext


def tokenize(ctx: NormalizationContext) -> NormalizationContext:
    """Final tokenization: split, clean, rejoin."""
    text = ctx.text
    # Remove remaining punctuation except hyphens within words and dots in numbers
    text = re.sub(r'[,;:!?()[\]{}]', ' ', text)
    # Split into tokens
    tokens = text.split()
    # Remove empty tokens and very short noise
    tokens = [t.strip() for t in tokens if len(t.strip()) > 0]
    ctx.tokens = tokens
    ctx.text = " ".join(tokens)
    return ctx
