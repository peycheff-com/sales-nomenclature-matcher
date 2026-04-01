# Scoring Formula v1

## Features (15)

| # | Feature | Type | Range |
|---|---------|------|-------|
| f1 | article_exact | binary | 0/1 |
| f2 | manufacturer_code_exact | binary | 0/1 |
| f3 | supplier_mapping_hit | binary | 0/1 |
| f4 | brand_exact | binary | 0/1 |
| f5 | brand_fuzzy | continuous | [0,1] |
| f6 | category_exact | binary | 0/1 |
| f7 | category_fuzzy | continuous | [0,1] |
| f8 | lexical_score | continuous | [0,1] |
| f9 | semantic_score | continuous | [0,1] |
| f10 | rerank_score | continuous | [0,1] |
| f11 | number_signature_score | continuous | [0,1] |
| f12 | packaging_match_score | discrete | 0/0.5/1 |
| f13 | unit_match_score | binary | 0/1 |
| f14 | attribute_overlap_score | continuous | [0,1] |
| f15 | alias_hit | binary | 0/1 |

## Short-Circuit Paths

1. supplier_mapping_hit == 1 AND mapping_type in {exact, approved} → score=0.995, auto_match
2. article_exact == 1 AND brand_exact == 1 → score=0.985, auto_match

## Base Score Formula

```
base_score =
    0.08 * brand_exact +
    0.04 * brand_fuzzy +
    0.06 * category_exact +
    0.03 * category_fuzzy +
    0.12 * lexical_score +
    0.18 * semantic_score +
    0.26 * rerank_score +
    0.14 * number_signature_score +
    0.03 * packaging_match_score +
    0.02 * unit_match_score +
    0.03 * attribute_overlap_score +
    0.01 * alias_hit
```

Sum of weights = 1.00

## Bonuses

- article_exact == 1: +0.05
- manufacturer_code_exact == 1: +0.05
- brand_exact == 1 AND number_signature_score >= 0.9: +0.03
- alias_hit == 1: +0.02

## Penalties

- critical_number_conflict: -0.18
- category_conflict: -0.15
- packaging_conflict: -0.12
- unit_conflict: -0.10
- brand_conflict (without article/mfr code match): -0.08

## Hard Gates (block auto_match)

1. critical_number_conflict AND NOT article_exact AND NOT manufacturer_code_exact
2. category_conflict AND rerank_score < 0.95
3. brand_conflict AND number_signature_score < 0.6

## Decision Thresholds

| Mode | auto_match | review_needed | no_match |
|------|-----------|--------------|----------|
| balanced | >= 0.93 | 0.75 - 0.9299 | < 0.75 |
| strict | >= 0.96 | 0.80 - 0.9599 | < 0.80 |

## Final Score

```
raw_final = base_score + rules_bonus + rules_penalty
final_score = min(1.0, max(0.0, raw_final))
```
