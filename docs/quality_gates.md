# Quality Gates / Quality Gates

## English

### Overview

The quality gate system prevents index activation when quality metrics regress beyond defined thresholds. This ensures that reindexing (e.g., new embedding model) doesn't silently degrade match quality.

### Gate Thresholds

| Metric | Max Regression | Description |
|--------|---------------|-------------|
| Top-1 Accuracy | 2% drop | Best candidate is correct product |
| Top-3 Recall | 3% drop | Correct product in top 3 candidates |
| FP Rate | 1% increase | Auto-match items that are incorrect |

### How It Works

1. **Reindex completes** — new embeddings generated, new index version created
2. **Quality evaluation runs** — golden set items matched against new index
3. **Comparison** — new metrics compared against most recent quality report
4. **Gate decision:**
   - **PASS**: new index activated, quality report saved
   - **FAIL**: old index stays active, regressions reported in response

### Golden Set

Stored in `golden_labels` table. Created automatically from review actions:
- `positive` — accepted/corrected matches (correct product identified)
- `negative` — rejected matches (no correct product)
- `ambiguous` — edge cases

#### Managing the Golden Set

- Labels are auto-created during review (`POST /api/v1/review/items/{id}`)
- Labels can be versioned via `version` field
- Deactivate outdated labels with `is_active = false`

### Metrics Endpoints

- `GET /api/v1/metrics/quality` — current metrics (filterable by supplier/category)
- `GET /api/v1/metrics/quality/history` — time-series for trend analysis

### Supplier-Level Thresholds

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

## Русский

### Обзор

Система quality gates не активирует новый search index, если quality metrics
регрессируют сильнее заданных thresholds. Это защищает reindexing, например
при смене embedding model, от незаметного ухудшения качества сопоставления.

### Thresholds

| Metric | Max Regression | Описание |
|--------|---------------|----------|
| Top-1 Accuracy | 2% drop | Лучший кандидат является правильным товаром |
| Top-3 Recall | 3% drop | Правильный товар входит в top 3 candidates |
| FP Rate | 1% increase | Auto-match позиции, которые оказались неверными |

### Как это работает

1. **Reindex завершен** - созданы новые embeddings и новая index version.
2. **Quality evaluation запускается** - golden set items сопоставляются с новым index.
3. **Comparison** - новые metrics сравниваются с последним quality report.
4. **Gate decision:**
   - **PASS**: новый index активируется, quality report сохраняется.
   - **FAIL**: старый index остается активным, regressions возвращаются в response.

### Golden Set

Golden set хранится в таблице `golden_labels` и создается из review actions:

- `positive` - accepted/corrected matches, где правильный товар найден.
- `negative` - rejected matches, где правильного товара нет.
- `ambiguous` - edge cases.

#### Управление Golden Set

- Labels создаются автоматически при review (`POST /api/v1/review/items/{id}`).
- Labels можно versioned через поле `version`.
- Устаревшие labels отключаются через `is_active = false`.

### Metrics Endpoints

- `GET /api/v1/metrics/quality` - текущие metrics, фильтруемые по supplier/category.
- `GET /api/v1/metrics/quality/history` - time-series для trend analysis.

### Supplier-Level Thresholds

Поставщики могут иметь custom thresholds в `normalization_rules.thresholds`:

```json
{
  "thresholds": {
    "auto_threshold": 0.95,
    "review_threshold": 0.80
  }
}
```

Эти значения переопределяют global thresholds для позиций конкретного supplier.
