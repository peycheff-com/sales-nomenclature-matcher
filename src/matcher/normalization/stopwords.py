from __future__ import annotations

from matcher.normalization.pipeline import NormalizationContext, load_config


def remove_stopwords(ctx: NormalizationContext) -> NormalizationContext:
    """Remove stopwords from text."""
    config = load_config()
    stopwords = set(w.lower() for w in config.get("stopwords", []))

    tokens = ctx.text.split()
    filtered = [t for t in tokens if t.lower() not in stopwords]
    ctx.text = " ".join(filtered)
    return ctx
