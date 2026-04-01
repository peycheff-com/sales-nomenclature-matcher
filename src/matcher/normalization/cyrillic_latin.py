from __future__ import annotations

import re

from matcher.normalization.pipeline import NormalizationContext, load_config

# Confusable pairs: Latin char -> Cyrillic equivalent
_LATIN_TO_CYR = {
    'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р',
    'x': 'х', 'y': 'у', 'k': 'к', 'h': 'н', 't': 'т',
    'b': 'в', 'm': 'м',
}
_CYR_TO_LATIN = {v: k for k, v in _LATIN_TO_CYR.items()}


def _is_cyrillic(ch: str) -> bool:
    return '\u0400' <= ch <= '\u04ff'


def _is_latin(ch: str) -> bool:
    return ('a' <= ch <= 'z') or ('A' <= ch <= 'Z')


def _normalize_token(token: str) -> str:
    """Normalize a mixed-script token to one script."""
    cyr_count = sum(1 for c in token if _is_cyrillic(c))
    lat_count = sum(1 for c in token if _is_latin(c))

    if cyr_count == 0 or lat_count == 0:
        return token  # Already single-script

    # Majority wins
    if cyr_count >= lat_count:
        # Convert Latin confusables to Cyrillic
        return "".join(_LATIN_TO_CYR.get(c, c) for c in token)
    else:
        # Convert Cyrillic confusables to Latin
        return "".join(_CYR_TO_LATIN.get(c, c) for c in token)


def cyrillic_latin_normalize(ctx: NormalizationContext) -> NormalizationContext:
    """Normalize mixed Cyrillic/Latin tokens to single script."""
    # Normalize x/х multiplier signs to standard 'x'
    text = re.sub(r'(?<=\d)\s*[хХxX×]\s*(?=\d)', 'x', ctx.text)

    # Process each token for mixed-script normalization
    parts = text.split()
    normalized_parts = [_normalize_token(p) for p in parts]
    ctx.text = " ".join(normalized_parts)
    return ctx
