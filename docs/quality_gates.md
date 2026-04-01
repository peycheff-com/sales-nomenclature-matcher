# Quality Gates

## Overview

The quality gate system prevents index activation when quality metrics regress beyond defined thresholds. This ensures that reindexing (e.g., new embedding model) doesn't silently degrade match quality.

## Gate Thresholds

| Metric | Max Regression | Description |
|--------|---------------|-------------|
| Top-1 Accuracy | 2% drop | Best candidate is correct product |
| Top-3 Recall | 3% drop | Correct product in top 3 candidates |
| FP Rate | 1% increase | Auto-match items that are incorrect |

## How It Works

1. **Reindex completes** — new embeddings generated, new index version created
2. **Quality evaluation runs** — golden set items matched against new index
3. **Comparison** — new metrics compared against most recent quality report
4. **Gate decision:**
   - **PASS**: new index activated, quality report saved
   - **FAIL**: old index stays active, regressions reported in response

## Golden Set

Stored in `golden_labels` table. Created automatically from review actions:
- `positive` — accepted/corrected matches (correct product identified)
- `negative` — rejected matches (no correct product)
- `ambiguous` — edge cases

### Managing the Golden Set

- Labels are auto-created during review (`POST /api/v1/review/items/{id}`)
- Labels can be versioned via `version` field
- Deactivate outdated labels with `is_active = false`

## Metrics Endpoints

- `GET /api/v1/metrics/quality` — current metrics (filterable by supplier/category)
- `GET /api/v1/metrics/quality/history` — time-series for trend analysis

## Supplier-Level Thresholds

Suppliers can have custom thresholds in `normalization_rules.thresholds`:

```json
{
  "thresholds": {
    "auto_threshold": 0.95,
    "review_threshold": 0.80
  }
}
```

These override global thresholds for that supplier's items.
