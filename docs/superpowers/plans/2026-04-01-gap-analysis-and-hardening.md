# Gap Analysis & Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all confirmed bugs, close spec-vs-implementation gaps, and harden the system for production readiness.

**Architecture:** The codebase is ~85% complete. This plan addresses 4 confirmed bugs, 6 functional gaps, 4 frontend gaps, and 3 infrastructure issues — organized from critical fixes through feature completion to hardening.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy async, arq), PostgreSQL 16 + pgvector, Redis 7, React 19 + Vite + TanStack + shadcn/ui.

---

## Gap Summary

### Confirmed Bugs (P0)

| # | Bug | Location | Impact |
|---|-----|----------|--------|
| B1 | `datetime.utcnow()` produces naive datetimes | `src/matcher/db/repos/match.py:65,66,285` | Comparison with `timestamptz` columns is undefined behavior |
| B2 | `article_hint=features.brand` passes wrong field | `src/matcher/pipeline/orchestrator.py:73` | Hybrid search can't match by article — exact-match CTE broken |
| B3 | Failed batch items silently counted as `no_match` | `src/matcher/worker/tasks.py:100-103` | Errors invisible to operators; inflated no_match counts |
| B4 | Decision thresholds hardcoded, ignore settings | `src/matcher/pipeline/decision.py:20-21` | `PUT /settings` threshold changes have no effect |

### Functional Gaps (P1)

| # | Gap | Location | Spec Reference |
|---|-----|----------|----------------|
| G1 | Alias lookup never performed — `f15 alias_hit` always 0 | `orchestrator.py` | scoring_v1.md feature f15 |
| G2 | `attribute_overlap_score` (f14) always 0 — extractor stubbed | `pipeline/features.py` | scoring_v1.md weight 0.03 |
| G3 | Settings (1C, thresholds) only in memory — lost on restart | `api/v1/settings.py:81` | production-readiness-design Phase 13 |
| G4 | `normalization_synonyms` table populated but never queried | `normalization/pipeline.py` | ddl_v1.sql table definition |
| G5 | No concurrency guard on catalog import — parallel imports corrupt | `worker/tasks.py` | production-readiness-design Phase 4 |
| G6 | Worker doesn't record per-item errors in DB | `worker/tasks.py:61` | `decision_trace_json` column unused |

### Frontend Gaps (P2)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| F1 | Review "Correct" dialog requires raw UUID — no product search | `review-actions.tsx` | Operators can't correct matches without external lookup |
| F2 | Import/reindex show job_id but don't poll for completion | `admin.tsx` | No progress feedback for long-running jobs |
| F3 | No supplier mapping creation UI | — | OpenAPI `/suppliers/{id}/mappings` not exposed |
| F4 | No error boundaries — unhandled exceptions crash entire SPA | `App.tsx` | Single React error takes down whole app |

### Infrastructure Gaps (P3)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| I1 | `effective_cache_size=6GB` on 3GB container | `infra/postgres/postgresql.conf` | Planner makes wrong decisions, possible OOM |
| I2 | No `statement_timeout` — runaway queries block workers | `infra/postgres/postgresql.conf` | Hung queries hold connections indefinitely |
| I3 | Nginx has no security headers (CSP, X-Frame-Options, etc.) | `infra/nginx/nginx.conf` | Clickjacking, XSS amplification risk |

---

## Task List

### Task 1: Fix naive datetime bug (B1)

**Files:**
- Modify: `src/matcher/db/repos/match.py:65,66,285`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api/test_match_timestamps.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from matcher.db.repos.match import MatchRepo


@pytest.mark.asyncio
async def test_update_request_status_uses_timezone_aware_datetime(mock_db_session):
    repo = MatchRepo(mock_db_session)
    mock_db_session.execute = AsyncMock()

    await repo.update_request_status("req_123", "running")

    call_args = mock_db_session.execute.call_args
    # Extract the compiled values from the UPDATE statement
    stmt = call_args[0][0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    params = compiled.params
    started_at = params.get("started_at")
    assert started_at is not None
    assert started_at.tzinfo is not None, "started_at must be timezone-aware"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_api/test_match_timestamps.py -v`
Expected: FAIL — `started_at.tzinfo` is None because `datetime.utcnow()` returns naive datetime.

- [ ] **Step 3: Fix all three occurrences**

In `src/matcher/db/repos/match.py`, replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`:

Line 65: `values["started_at"] = datetime.now(timezone.utc)`
Line 67: `values["finished_at"] = datetime.now(timezone.utc)`
Line 285: `reviewed_at=datetime.now(timezone.utc),`

Also remove the unused `UTC` import on line 4 if present (keep `timezone`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_api/test_match_timestamps.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/ -x -q`
Expected: All existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/matcher/db/repos/match.py tests/test_api/test_match_timestamps.py
git commit -m "fix: use timezone-aware datetimes in MatchRepo (B1)"
```

---

### Task 2: Fix article_hint parameter bug (B2)

**Files:**
- Modify: `src/matcher/pipeline/orchestrator.py:69-75`
- Modify: `src/matcher/pipeline/features.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_article_hint.py
import re
from matcher.normalization.pipeline import run_pipeline
from matcher.pipeline.features import extract_features


def test_article_extracted_from_normalization():
    """Article codes in input should be extractable, not confused with brand."""
    ctx = run_pipeline("Насос Grundfos UPS 25-40 арт.96281375")
    features = extract_features(ctx)
    # Brand should be grundfos, not the article number
    assert features.brand == "grundfos"
    # Article should be extracted separately
    assert features.article is not None
    assert "96281375" in features.article
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/test_article_hint.py -v`
Expected: FAIL — `ExtractedFeatures` has no `article` attribute.

- [ ] **Step 3: Add article extraction to ExtractedFeatures**

In `src/matcher/pipeline/features.py`, add `article` field to the dataclass:

```python
@dataclass
class ExtractedFeatures:
    brand: str | None = None
    article: str | None = None  # <-- add this
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
            "article": self.article,  # <-- add this
            "model": self.model,
            "numbers": self.numbers,
            "dimensions": self.dimensions,
            "unit": self.unit,
            "packaging": self.packaging,
            "material": self.material,
            "category_guess": self.category_guess,
        }
```

Add article extraction logic to `extract_features()`:

```python
import re

_ARTICLE_PATTERN = re.compile(
    r'(?:арт\.?|art\.?|код|code)\s*[:№#]?\s*([A-Za-z0-9\-\.]+)',
    re.IGNORECASE,
)

def extract_features(ctx: NormalizationContext) -> ExtractedFeatures:
    """Extract structured features from normalization context."""
    config = load_config()
    packaging_kw = set(w.lower() for w in config.get("packaging_keywords", []))

    # Try to extract article from the original (pre-normalized) text
    article = None
    # NormalizationContext stores the normalized text; re-check tokens for article-like patterns
    for token in ctx.tokens:
        if re.match(r'^\d{6,}$', token):
            article = token
            break

    features = ExtractedFeatures(
        brand=ctx.brand,
        article=article,
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

    return features
```

- [ ] **Step 4: Fix orchestrator to use features.article**

In `src/matcher/pipeline/orchestrator.py:73`, change:

```python
# Before:
article_hint=features.brand,  # Could also try article extraction
# After:
article_hint=features.article,
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/test_article_hint.py tests/test_pipeline/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/matcher/pipeline/features.py src/matcher/pipeline/orchestrator.py tests/test_pipeline/test_article_hint.py
git commit -m "fix: extract article codes and pass correct hint to search (B2)"
```

---

### Task 3: Fix silent batch error handling (B3 + G6)

**Files:**
- Modify: `src/matcher/worker/tasks.py:100-103`
- Modify: `src/matcher/db/repos/match.py` (add `update_item_error` method)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_worker/test_batch_error_tracking.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from matcher.worker.tasks import batch_match


@pytest.mark.asyncio
async def test_batch_match_records_item_errors():
    """Failed items should be recorded with error details, not silently counted as no_match."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_item = MagicMock()
    mock_item.request_item_id = "item_test123"
    mock_item.raw_text = "test product"
    mock_item.line_id = "1"

    mock_request = MagicMock()
    mock_request.supplier_id = None

    mock_repo = AsyncMock()
    mock_repo.get_request.return_value = mock_request
    mock_repo.get_request_items.return_value = ([mock_item], 1)

    ctx = {"db_factory": AsyncMock()}
    ctx["db_factory"].return_value.__aenter__ = AsyncMock(return_value=mock_session)
    ctx["db_factory"].return_value.__aexit__ = AsyncMock()

    with patch("matcher.worker.tasks.MatchRepo", return_value=mock_repo), \
         patch("matcher.worker.tasks.match_single", side_effect=RuntimeError("embedding failed")):
        result = await batch_match(ctx, "req_test")

    # Verify item was updated with error status and message
    mock_repo.update_item_result.assert_called_once()
    call_kwargs = mock_repo.update_item_result.call_args[1]
    assert call_kwargs["status"] == "no_match"
    assert "embedding failed" in (call_kwargs.get("decision_trace_json", {}) or {}).get("error", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_worker/test_batch_error_tracking.py -v`
Expected: FAIL — `update_item_result` is never called for errored items.

- [ ] **Step 3: Fix error handling in batch_match**

In `src/matcher/worker/tasks.py`, replace the except block (lines 100-103):

```python
                except Exception as exc:
                    logger.exception("Error processing item %s", item.request_item_id)
                    await repo.update_item_result(
                        item.request_item_id,
                        status="no_match",
                        confidence=0.0,
                        decision_trace_json={"error": str(exc), "stage": "pipeline"},
                    )
                    no_match_count += 1
                    processed += 1
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_worker/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matcher/worker/tasks.py tests/test_worker/test_batch_error_tracking.py
git commit -m "fix: record per-item errors in decision_trace_json (B3+G6)"
```

---

### Task 4: Wire decision thresholds from settings (B4)

**Files:**
- Modify: `src/matcher/pipeline/decision.py`
- Modify: `src/matcher/pipeline/orchestrator.py`
- Modify: `src/matcher/worker/tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_decision_thresholds.py
from matcher.pipeline.scoring import ScoringResult, PairFeatures
from matcher.pipeline.decision import decide


def test_decide_uses_custom_thresholds():
    """Decision function should accept custom thresholds, not just strict_mode toggle."""
    features = PairFeatures(rerank_score=0.9, semantic_score=0.8, lexical_score=0.7)
    scoring = ScoringResult(final_score=0.91, features=features)

    # With default balanced (0.93) → review_needed
    result_default = decide(scoring, strict_mode=False)
    assert result_default.status == "review_needed"

    # With custom lower threshold (0.90) → auto_match
    result_custom = decide(scoring, auto_threshold=0.90, review_threshold=0.75)
    assert result_custom.status == "auto_match"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/test_decision_thresholds.py -v`
Expected: FAIL — `decide()` doesn't accept `auto_threshold`/`review_threshold` params.

- [ ] **Step 3: Add threshold parameters to decide()**

In `src/matcher/pipeline/decision.py`:

```python
def decide(
    scoring: ScoringResult,
    strict_mode: bool = False,
    auto_threshold: float | None = None,
    review_threshold: float | None = None,
) -> MatchDecision:
    """Apply decision thresholds to a scoring result."""
    if auto_threshold is None:
        auto_threshold = 0.96 if strict_mode else 0.93
    if review_threshold is None:
        review_threshold = 0.80 if strict_mode else 0.75

    score = scoring.final_score
    forbidden = scoring.auto_match_forbidden

    if score >= auto_threshold and not forbidden:
        status = "auto_match"
    elif score >= review_threshold:
        status = "review_needed"
    else:
        status = "no_match"

    return MatchDecision(
        status=status,
        confidence=score,
        auto_match_forbidden=forbidden,
    )
```

- [ ] **Step 4: Pass settings thresholds through orchestrator**

In `src/matcher/pipeline/orchestrator.py`, add threshold params to `match_single()`:

```python
async def match_single(
    raw_text: str,
    session: AsyncSession,
    line_id: str | None = None,
    supplier_id: str | None = None,
    strict_mode: bool = False,
    retrieval_top_n: int = 50,
    rerank_top_n: int = 10,
    auto_threshold: float | None = None,
    review_threshold: float | None = None,
) -> MatchItemResult:
```

And pass them through to `decide()` on line 140:

```python
        decision = decide(
            scoring_result,
            strict_mode=strict_mode,
            auto_threshold=auto_threshold,
            review_threshold=review_threshold,
        )
```

In `src/matcher/worker/tasks.py`, pass settings values in the `match_single` call (line 41):

```python
from matcher.config import settings

# ... inside the for loop:
                    result = await match_single(
                        raw_text=item.raw_text,
                        session=session,
                        line_id=item.line_id,
                        supplier_id=request.supplier_id,
                        auto_threshold=settings.auto_match_threshold,
                        review_threshold=settings.review_threshold,
                    )
```

- [ ] **Step 5: Run all pipeline + worker tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/ tests/test_worker/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/matcher/pipeline/decision.py src/matcher/pipeline/orchestrator.py src/matcher/worker/tasks.py tests/test_pipeline/test_decision_thresholds.py
git commit -m "fix: wire settings thresholds into decision logic (B4)"
```

---

### Task 5: Add alias lookup to matching pipeline (G1)

**Files:**
- Create: `src/matcher/db/repos/alias.py`
- Modify: `src/matcher/pipeline/orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_alias_lookup.py
import pytest
from unittest.mock import AsyncMock, patch

from matcher.db.repos.alias import AliasRepo


@pytest.mark.asyncio
async def test_alias_repo_find_by_text(mock_db_session):
    """AliasRepo should find aliases matching normalized text."""
    mock_result = AsyncMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    repo = AliasRepo(mock_db_session)
    result = await repo.find_by_normalized_text("насос grundfos")
    assert result == []
    mock_db_session.execute.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/test_alias_lookup.py -v`
Expected: FAIL — `matcher.db.repos.alias` module does not exist.

- [ ] **Step 3: Create AliasRepo**

```python
# src/matcher/db/repos/alias.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.db.models import CatalogAlias


class AliasRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_normalized_text(self, normalized_text: str) -> list[CatalogAlias]:
        """Find aliases matching normalized text (exact or trigram)."""
        stmt = (
            select(CatalogAlias)
            .where(
                CatalogAlias.normalized_alias_text == normalized_text,
                CatalogAlias.is_active.is_(True) if hasattr(CatalogAlias, 'is_active') else True,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_product_ids_by_text(self, normalized_text: str) -> set[str]:
        """Return product_ids that have an alias matching the text."""
        aliases = await self.find_by_normalized_text(normalized_text)
        return {a.product_id for a in aliases}
```

- [ ] **Step 4: Wire alias lookup into orchestrator**

In `src/matcher/pipeline/orchestrator.py`, after candidate retrieval (around line 96) and before scoring (line 118), add alias product ID lookup. Then pass `alias_hit=True` to `compute_pair_features` when the candidate's product_id is in the alias set:

```python
    # Stage 3.5: Alias lookup
    from matcher.db.repos.alias import AliasRepo
    alias_repo = AliasRepo(session)
    alias_product_ids = await alias_repo.find_product_ids_by_text(normalized_text)
```

Then in the scoring loop, update the `compute_pair_features` call to pass:

```python
            alias_hit=c.product_id in alias_product_ids,
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/matcher/db/repos/alias.py src/matcher/pipeline/orchestrator.py tests/test_pipeline/test_alias_lookup.py
git commit -m "feat: add alias lookup to scoring pipeline (G1)"
```

---

### Task 6: Implement attribute_overlap_score (G2)

**Files:**
- Modify: `src/matcher/pipeline/features.py`
- Modify: `src/matcher/pipeline/orchestrator.py`
- Modify: `src/matcher/pipeline/scoring.py` (add `compute_attribute_overlap` helper)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline/test_attribute_overlap.py
from matcher.pipeline.scoring import compute_attribute_overlap


def test_attribute_overlap_identical():
    query_attrs = {"brand": "bosch", "unit": "шт", "numbers": [25, 40]}
    cand_attrs = {"brand": "bosch", "unit": "шт", "numbers": [25, 40]}
    assert compute_attribute_overlap(query_attrs, cand_attrs) == 1.0


def test_attribute_overlap_partial():
    query_attrs = {"brand": "bosch", "unit": "шт", "numbers": [25]}
    cand_attrs = {"brand": "bosch", "unit": "м", "numbers": [25]}
    score = compute_attribute_overlap(query_attrs, cand_attrs)
    assert 0.3 < score < 0.9  # partial overlap


def test_attribute_overlap_no_attributes():
    assert compute_attribute_overlap({}, {}) == 0.0


def test_attribute_overlap_none_values_ignored():
    query_attrs = {"brand": "bosch", "model": None}
    cand_attrs = {"brand": "bosch", "model": None}
    assert compute_attribute_overlap(query_attrs, cand_attrs) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/test_attribute_overlap.py -v`
Expected: FAIL — `compute_attribute_overlap` doesn't exist.

- [ ] **Step 3: Implement compute_attribute_overlap**

Add to `src/matcher/pipeline/scoring.py`:

```python
def compute_attribute_overlap(query_attrs: dict, candidate_attrs: dict) -> float:
    """Compute Jaccard-like overlap of non-None extracted attributes."""
    keys = set(query_attrs.keys()) | set(candidate_attrs.keys())
    # Only consider keys where at least one side has a non-None value
    comparable = []
    for k in keys:
        qv = query_attrs.get(k)
        cv = candidate_attrs.get(k)
        if qv is None and cv is None:
            continue
        comparable.append((qv, cv))

    if not comparable:
        return 0.0

    matches = 0
    for qv, cv in comparable:
        if qv is None or cv is None:
            continue
        if isinstance(qv, list) and isinstance(cv, list):
            qset, cset = set(str(x) for x in qv), set(str(x) for x in cv)
            if qset and cset:
                matches += len(qset & cset) / len(qset | cset)
        elif str(qv).lower().strip() == str(cv).lower().strip():
            matches += 1

    return matches / len(comparable)
```

- [ ] **Step 4: Wire into orchestrator scoring loop**

In `src/matcher/pipeline/orchestrator.py`, inside the scoring loop, compute candidate attributes and call `compute_attribute_overlap`:

```python
        # After compute_pair_features, before score_candidate:
        from matcher.pipeline.scoring import compute_attribute_overlap
        candidate_attrs = {
            "brand": c.normalized_brand or c.brand,
            "unit": c.unit,
            "numbers": candidate_numbers,
        }
        query_attrs = {
            "brand": features.brand,
            "unit": features.unit,
            "numbers": features.numbers,
        }
        pair_features.attribute_overlap_score = compute_attribute_overlap(query_attrs, candidate_attrs)
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_pipeline/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/matcher/pipeline/scoring.py src/matcher/pipeline/orchestrator.py tests/test_pipeline/test_attribute_overlap.py
git commit -m "feat: implement attribute_overlap_score computation (G2)"
```

---

### Task 7: Add Redis lock for catalog import concurrency (G5)

**Files:**
- Modify: `src/matcher/worker/tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_worker/test_import_lock.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_catalog_import_rejects_concurrent():
    """Second catalog import should fail if one is already running."""
    from matcher.worker.tasks import catalog_import

    mock_redis = AsyncMock()
    # Simulate lock already held
    mock_redis.set = AsyncMock(return_value=False)  # NX fails

    ctx = {"db_factory": AsyncMock(), "redis": mock_redis}
    result = await catalog_import(ctx, "job_2", "csv", file_url="http://example.com/f.csv")
    assert result["status"] == "failed"
    assert "already running" in result["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_worker/test_import_lock.py -v`
Expected: FAIL — no lock check in `catalog_import`.

- [ ] **Step 3: Add Redis-based lock to catalog_import**

In `src/matcher/worker/tasks.py`, at the top of `catalog_import()`:

```python
async def catalog_import(ctx: dict, job_id: str, source_type: str, **kwargs) -> dict:
    """Import catalog from CSV/XLSX file."""
    # Concurrency guard: only one import at a time
    redis = ctx.get("redis")
    lock_key = "lock:catalog_import"
    if redis:
        acquired = await redis.set(lock_key, job_id, ex=3600, nx=True)
        if not acquired:
            return {"job_id": job_id, "status": "failed", "error": "Another import is already running"}
    try:
        return await _do_catalog_import(ctx, job_id, source_type, **kwargs)
    finally:
        if redis:
            await redis.delete(lock_key)
```

Move the existing body into `_do_catalog_import()`.

- [ ] **Step 4: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_worker/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/matcher/worker/tasks.py tests/test_worker/test_import_lock.py
git commit -m "feat: add Redis lock to prevent concurrent catalog imports (G5)"
```

---

### Task 8: Fix PostgreSQL memory settings (I1 + I2)

**Files:**
- Modify: `infra/postgres/postgresql.conf`

- [ ] **Step 1: Fix effective_cache_size and add statement_timeout**

In `infra/postgres/postgresql.conf`, change:

```
# Before:
effective_cache_size = 6GB

# After:
effective_cache_size = 2GB
```

Add after the memory section:

```
# Safety
statement_timeout = 120000          # 2 minutes max per query
idle_in_transaction_session_timeout = 300000  # 5 minutes
```

- [ ] **Step 2: Verify config syntax**

Run: `cd /Users/ivan/Code/projects/1C && docker compose exec db postgres --check -c "config_file=/etc/postgresql/postgresql.conf" 2>&1 || echo "Syntax check requires running container — verify manually after deploy"`

- [ ] **Step 3: Commit**

```bash
git add infra/postgres/postgresql.conf
git commit -m "fix: correct effective_cache_size for 3GB container, add statement_timeout (I1+I2)"
```

---

### Task 9: Add Nginx security headers (I3)

**Files:**
- Modify: `infra/nginx/nginx.conf`

- [ ] **Step 1: Add security headers to server block**

In `infra/nginx/nginx.conf`, inside the `server` block (HTTPS), add:

```nginx
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

- [ ] **Step 2: Commit**

```bash
git add infra/nginx/nginx.conf
git commit -m "fix: add security headers to nginx config (I3)"
```

---

### Task 10: Add product search to Review "Correct" dialog (F1)

**Files:**
- Modify: `frontend/src/components/review/review-actions.tsx`
- Modify: `frontend/src/api/catalog.ts` (verify search endpoint exists)

- [ ] **Step 1: Add product search autocomplete to correction dialog**

In `frontend/src/components/review/review-actions.tsx`, replace the raw UUID text input in the correction dialog with a search-as-you-type component:

```tsx
// Inside the dialog content, replace the plain Input with:
const [searchQuery, setSearchQuery] = useState("")
const [searchResults, setSearchResults] = useState<Array<{product_id: string; name: string; article: string; brand: string}>>([])
const [searching, setSearching] = useState(false)

// Debounced search
useEffect(() => {
  if (searchQuery.length < 2) { setSearchResults([]); return }
  const timer = setTimeout(async () => {
    setSearching(true)
    try {
      const resp = await api.get("catalog/products", { searchParams: { q: searchQuery, limit: "10" } }).json<any>()
      setSearchResults(resp.products || [])
    } catch { setSearchResults([]) }
    finally { setSearching(false) }
  }, 300)
  return () => clearTimeout(timer)
}, [searchQuery])
```

Render a dropdown list below the search input showing product name, article, brand. Clicking a result fills `correctProductId`.

- [ ] **Step 2: Verify it works with catalog endpoint**

Run: `cd /Users/ivan/Code/projects/1C/frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/review/review-actions.tsx
git commit -m "feat: add product search to review correction dialog (F1)"
```

---

### Task 11: Add job polling to admin import/reindex (F2)

**Files:**
- Modify: `frontend/src/pages/admin.tsx`

- [ ] **Step 1: Add polling state after import/reindex triggers**

After `POST /catalog/import` or `POST /catalog/reindex` succeeds and returns a `job_id`, show a progress section that polls a relevant endpoint. Since there's no dedicated job status endpoint, show a "Job submitted" message with the job_id and a spinner that auto-hides after 10 seconds, plus a link to refresh metrics:

```tsx
const [activeJob, setActiveJob] = useState<{id: string; type: string; startedAt: number} | null>(null)

// After successful mutation:
onSuccess: (data) => {
  setActiveJob({ id: data.job_id, type: "import", startedAt: Date.now() })
  toast.success(`Задание ${data.job_id} запущено`)
}

// In render, show a status card:
{activeJob && (
  <Card>
    <CardContent className="py-3 flex items-center gap-3">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Задание {activeJob.type === "import" ? "импорта" : "переиндексации"}: {activeJob.id}</span>
      {Date.now() - activeJob.startedAt > 30000 && (
        <span className="text-sm text-muted-foreground">Выполняется дольше обычного...</span>
      )}
    </CardContent>
  </Card>
)}
```

- [ ] **Step 2: Build frontend**

Run: `cd /Users/ivan/Code/projects/1C/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/admin.tsx
git commit -m "feat: show job status feedback for import/reindex (F2)"
```

---

### Task 12: Add React error boundary (F4)

**Files:**
- Create: `frontend/src/components/error-boundary.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create error boundary component**

```tsx
// frontend/src/components/error-boundary.tsx
import { Component, type ErrorInfo, type ReactNode } from "react"
import { Button } from "@/components/ui/button"

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-center space-y-4 max-w-md">
            <h1 className="text-2xl font-bold">Что-то пошло не так</h1>
            <p className="text-muted-foreground">{this.state.error?.message}</p>
            <Button onClick={() => { this.setState({ hasError: false, error: null }); window.location.href = "/" }}>
              Вернуться на главную
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
```

- [ ] **Step 2: Wrap App with ErrorBoundary**

In `frontend/src/App.tsx`, wrap the `QueryClientProvider` with `<ErrorBoundary>`:

```tsx
import { ErrorBoundary } from "@/components/error-boundary"

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster position="top-right" richColors />
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
```

- [ ] **Step 3: Build frontend**

Run: `cd /Users/ivan/Code/projects/1C/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/error-boundary.tsx frontend/src/App.tsx
git commit -m "feat: add React error boundary for graceful crash recovery (F4)"
```

---

### Task 13: Add supplier mapping creation UI (F3)

**Files:**
- Modify: `frontend/src/pages/suppliers.tsx`
- Verify: `frontend/src/api/suppliers.ts` has `createMapping` function

- [ ] **Step 1: Add createMapping API function if missing**

In `frontend/src/api/suppliers.ts`, add:

```typescript
export async function createSupplierMapping(
  supplierId: string,
  data: {
    supplier_sku?: string
    supplier_article?: string
    supplier_raw_text: string
    product_id: string
    mapping_type: string
    confidence?: number
  }
) {
  return api.post(`suppliers/${supplierId}/mappings`, { json: data }).json()
}
```

- [ ] **Step 2: Add mapping creation dialog to suppliers page**

In `frontend/src/pages/suppliers.tsx`, add a "Добавить маппинг" button per supplier that opens a dialog with fields: `supplier_raw_text`, `product_id` (with the same search component from Task 10), `mapping_type` select (exact/approved/manual), and optional `supplier_sku`/`supplier_article`.

- [ ] **Step 3: Build frontend**

Run: `cd /Users/ivan/Code/projects/1C/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/suppliers.ts frontend/src/pages/suppliers.tsx
git commit -m "feat: add supplier mapping creation UI (F3)"
```

---

### Task 14: Settings persistence to DB (G3)

**Files:**
- Create: `src/matcher/db/repos/settings.py`
- Create: DB migration for `system_settings` table
- Modify: `src/matcher/api/v1/settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api/test_settings_persistence.py
import pytest
from unittest.mock import AsyncMock

from matcher.db.repos.settings import SettingsRepo


@pytest.mark.asyncio
async def test_settings_repo_save_and_load(mock_db_session):
    mock_db_session.execute = AsyncMock()
    mock_db_session.flush = AsyncMock()
    repo = SettingsRepo(mock_db_session)
    # Should not raise
    await repo.upsert("onec_base_url", "http://1c.local")
    mock_db_session.execute.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_api/test_settings_persistence.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create system_settings table migration**

```bash
cd /Users/ivan/Code/projects/1C && python -m alembic revision --autogenerate -m "add_system_settings"
```

Then edit the generated migration to create a simple key-value table:

```python
def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("system_settings")
```

- [ ] **Step 4: Create SettingsRepo**

```python
# src/matcher/db/repos/settings.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, key: str, value: str | None) -> None:
        await self.session.execute(
            text("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (:key, :value, now())
                ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = now()
            """),
            {"key": key, "value": value},
        )

    async def get(self, key: str, default: str | None = None) -> str | None:
        result = await self.session.execute(
            text("SELECT value FROM system_settings WHERE key = :key"),
            {"key": key},
        )
        row = result.first()
        return row[0] if row else default

    async def get_all(self) -> dict[str, str]:
        result = await self.session.execute(text("SELECT key, value FROM system_settings"))
        return {row[0]: row[1] for row in result.all()}
```

- [ ] **Step 5: Wire into settings endpoint**

In `src/matcher/api/v1/settings.py`, on `PUT /settings` — after updating in-memory settings, also persist 1C and threshold settings to DB via `SettingsRepo`. On app startup (`GET /settings` first call or lifespan), load persisted settings.

- [ ] **Step 6: Run tests**

Run: `cd /Users/ivan/Code/projects/1C && python -m pytest tests/test_api/test_settings_persistence.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/matcher/db/repos/settings.py migrations/versions/ tests/test_api/test_settings_persistence.py src/matcher/api/v1/settings.py
git commit -m "feat: persist runtime settings to system_settings table (G3)"
```

---

## Execution Order

```
B1 (datetime)  ─┐
B2 (article)   ─┤── Can run in parallel (independent)
B3+G6 (errors) ─┤
B4 (thresholds)─┘
       │
       ▼
G1 (aliases)   ─┐
G2 (attributes)─┤── Can run in parallel (independent)
G5 (lock)      ─┘
       │
       ▼
I1+I2 (postgres)─┐
I3 (nginx)      ─┤── Can run in parallel (independent)
                 ┘
       │
       ▼
F1 (product search) ──→ F3 (supplier mapping, reuses search)
F2 (job polling)     ─┐
F4 (error boundary)  ─┤── Can run in parallel
                      ┘
       │
       ▼
G3 (settings persistence) ── Last (depends on stable API)
```

---

## Not In Scope (Future Work)

These items surfaced during review but are separate projects:

1. **1C OData API adapter** — requires Kerberos auth R&D, separate spike
2. **Token refresh mechanism** — needs frontend + backend JWT refresh flow design
3. **normalization_synonyms integration** (G4) — needs synonym matching strategy decision
4. **Batch review UI** — UX design needed before implementation
5. **Mobile responsive layout** — CSS-only, no logic changes
6. **Prometheus metrics** — observability layer, separate initiative
7. **Backup verification** — ops runbook, not code
