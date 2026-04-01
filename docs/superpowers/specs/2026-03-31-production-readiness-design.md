# Production-Ready Ship Plan: Sales Nomenclature Matcher

## Context

The customer needs a working tool for their sales department: upload client product lists, automatically match against their 1C catalog (tens of thousands of SKUs), review uncertain matches, and learn from approved mappings. The customer pays only on delivery of a fully working product.

**Current state:** ~60% done. The core matching pipeline (normalization, hybrid search, scoring, reranking) is solid and complete. What's missing: half the API endpoints are stubs, batch processing isn't wired, no auth, no frontend, no production deployment config.

**Target:** Single DigitalOcean droplet running Docker Compose, fully functional backend + React frontend, JWT auth, sample data for demo.

---

## Phase 0: Cleanup

**Goal:** Remove dead code, fix Dockerfile bug.

| Action | File |
|--------|------|
| Delete entire `app/` directory (17 files) | `app/**` |
| Fix Dockerfile: `COPY alembic ./alembic` → `COPY migrations ./migrations` | `Dockerfile:22` |

---

## Phase 1: Repository Layer

**Goal:** Replace raw `text()` SQL scattered across endpoints with typed repo classes.

**Create files in `src/matcher/db/repos/`:**

| File | Key Methods |
|------|-------------|
| `catalog.py` — CatalogRepo | `get_product()`, `upsert_products()`, `count_active()`, `get_products_needing_embedding()`, `upsert_embedding()`, `create_alias()` |
| `supplier.py` — SupplierRepo | `list_suppliers()`, `get_supplier()`, `create_mapping()`, `find_mapping()` |
| `match.py` — MatchRepo | `create_request()`, `create_items()`, `get_request()`, `get_request_items()`, `update_request_status()`, `update_item_result()`, `save_candidates()`, `get_item_candidates()`, `update_item_review()` |
| `metrics.py` — MetricsRepo | `compute_quality_metrics()`, `save_quality_report()` |
| `user.py` — UserRepo | `get_by_username()`, `create_user()` |
| `__init__.py` | Re-export all repos |

**Design:** Each repo takes `AsyncSession` in constructor. Injected via FastAPI `Depends`. Uses SQLAlchemy 2.x `select()`/`insert()`/`update()` against existing ORM models in `src/matcher/db/models.py`.

---

## Phase 2: Authentication

**Goal:** JWT auth with username/password login.

**New Alembic migration** — `migrations/versions/xxxx_add_users.py`:
```sql
CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  hashed_password TEXT NOT NULL,
  full_name TEXT,
  role TEXT NOT NULL DEFAULT 'operator' CHECK (role IN ('admin','operator','viewer')),
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**New dependencies in `pyproject.toml`:** `pyjwt>=2.8`, `passlib[bcrypt]>=1.7`

**Create files:**

| File | Purpose |
|------|---------|
| `src/matcher/auth/__init__.py` | Package init |
| `src/matcher/auth/security.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_access_token()` |
| `src/matcher/auth/deps.py` | `get_current_user()` (OAuth2PasswordBearer → decode JWT → lookup user), `require_role(*roles)` |
| `src/matcher/api/v1/auth.py` | `POST /api/v1/auth/login` (accepts OAuth2PasswordRequestForm, returns JWT), `GET /api/v1/auth/me` |

**Modify `src/matcher/config.py`:** Add `jwt_secret_key`, `jwt_algorithm="HS256"`, `jwt_expire_minutes=480`

**Modify `src/matcher/db/models.py`:** Add `User` ORM model

**Create `scripts/create_admin.py`:** CLI script to create initial admin user with prompted password

---

## Phase 3: App Infrastructure

**Goal:** Production-ready app initialization — arq pool, CORS, logging, health checks, middleware.

**Modify `src/matcher/main.py`:**
- **Lifespan:** Initialize arq Redis pool on startup → `app.state.arq_pool`, close on shutdown
- **CORS:** `CORSMiddleware` with origins from `settings.cors_origins`
- **Register auth router:** `app.include_router(auth.router, prefix="/api/v1")`
- **Health endpoint:** Check DB (`SELECT 1`) and Redis (`ping`), return `{"status": "ok"|"degraded", "checks": {...}}`

**Modify `src/matcher/config.py`:** Add `cors_origins: list[str] = ["*"]`, `log_level: str = "INFO"`

**Create files:**

| File | Purpose |
|------|---------|
| `src/matcher/logging_config.py` | JSON log formatter (stdlib `logging`, no new deps), configure on app startup |
| `src/matcher/api/middleware.py` | `RequestIdMiddleware` — generate UUID, store in contextvar, add `X-Request-ID` header, log request method/path/status/duration |

**Modify `src/matcher/api/deps.py`:** Add `get_arq_pool(request: Request) -> ArqRedis` dependency

---

## Phase 4: Complete Catalog Endpoints + Worker

**Goal:** Catalog import and reindex via API, processed by arq worker.

**Modify `src/matcher/api/v1/catalog.py`:**
- `POST /catalog/import` — validate input, enqueue arq job `catalog_import`, return `JobAccepted`. Requires `admin`/`operator` role.
- `POST /catalog/reindex` — enqueue arq job `catalog_reindex`, return `JobAccepted`. Requires `admin` role.

**Modify `src/matcher/worker/tasks.py`** — implement `catalog_import`:
- Download file from `file_url` (httpx), save to temp path
- Call `parse_file()` from `src/matcher/ingestion/file_adapter.py`
- Call `transform_item()` from `src/matcher/ingestion/transformer.py` for each row
- Use `CatalogRepo.upsert_products()` to bulk insert/update
- Log progress and results

**Modify `src/matcher/worker/settings.py`:**
- Add startup hook: initialize `ctx["db_factory"] = async_session_factory`
- Add shutdown hook: dispose engine

**Modify `src/matcher/indexing/indexer.py`:** Accept `session_factory` parameter instead of creating own engine

---

## Phase 5: Wire Batch Match

**Goal:** Batch match endpoint enqueues arq job, worker processes all items through the pipeline.

**Modify `src/matcher/api/v1/match.py`:**
- Replace raw SQL with `MatchRepo` calls
- After storing request + items, enqueue: `await arq_pool.enqueue_job("batch_match", request_id)`
- Add auth dependency to all endpoints
- In `match_sync`: also persist request/items/candidates to DB for history

**Modify `src/matcher/worker/tasks.py`** — implement `batch_match`:
- Load `MatchRequest` and items from DB
- Update request status to `running`, set `started_at`
- For each item: call `match_single()`, update item with results, save candidates, increment counters
- On completion: status → `done`, set `finished_at`
- On error: status → `failed`, set `error_message`
- Process in batches to avoid long transactions

---

## Phase 6: Complete Supplier Endpoints

**Goal:** List suppliers and create mappings.

**Modify `src/matcher/api/v1/suppliers.py`:**
- `GET /suppliers` — `SupplierRepo.list_suppliers()`, requires auth
- `POST /suppliers/{supplier_id}/mappings` — validate supplier exists, normalize `supplier_raw_text` via pipeline, `SupplierRepo.create_mapping()`, requires `admin`/`operator`

---

## Phase 7: Complete Metrics Endpoint

**Goal:** Quality metrics from reviewed data.

**Modify `src/matcher/api/v1/metrics.py`:**
- `GET /metrics/quality` — `MetricsRepo.compute_quality_metrics(supplier_id, category_id)`
- Computes: `top1_accuracy`, `top3_recall`, `precision_at_1`, `auto_match_false_positive_rate`, `review_acceptance_rate`, `avg_latency_ms`
- Queries `match_request_items` where `final_decision IS NOT NULL`
- Supports filtering by `supplier_id` and `category_id`

---

## Phase 8: Refactor Review Endpoint

**Goal:** Use repos, proper auth, golden labels creation.

**Modify `src/matcher/api/v1/review.py`:**
- Replace raw SQL with `MatchRepo`, `SupplierRepo`, `CatalogRepo` calls
- Use `current_user.username` for `reviewed_by` (currently hardcoded `'api_user'`)
- On finalized review: auto-create `golden_labels` entry (`positive` for accepted, `negative` for rejected, `positive` with corrected product for corrected)

---

## Phase 9: Sample Data

**Goal:** Realistic demo data for testing and customer presentation.

**Create `scripts/seed_sample_data.py`:**
- Generate 10K-15K construction/industrial product entries using templates:
  `{brand} {product_type} {article} {dimensions} {unit}`
- Use brands from `configs/normalization.yaml` (Knauf, Hilti, Bosch, Grundfos, Valtec, Schneider, ABB, etc.)
- Categories: pipes, cables, insulation, fasteners, paint, pumps, tools, plumbing fittings, electrical, drywall
- Run through `normalization.pipeline.run_pipeline()` to populate `normalized_name`, `search_document`
- Insert via `CatalogRepo.upsert_products()`

**Create `scripts/seed_test_queries.py`:**
- Generate 200-500 "client-style" queries (misspellings, abbreviations, different ordering) that map to the catalog
- Used for end-to-end validation of matching quality

---

## Phase 10: Frontend

**Goal:** React SPA for the sales team workflow.

### Tech Stack
React 19, Vite, TypeScript, TanStack Router + Query + Table, shadcn/ui, Tailwind CSS, ky (HTTP client), papaparse (CSV parsing), xlsx (export)

### Project Structure
```
frontend/
├── src/
│   ├── main.tsx, app.tsx, globals.css
│   ├── api/          — client.ts, types.ts, auth.ts, match.ts, review.ts, suppliers.ts, catalog.ts, metrics.ts
│   ├── hooks/        — use-auth.ts, use-batch-polling.ts, use-csv-parser.ts, use-export.ts
│   ├── lib/          — utils.ts, auth-store.ts, format.ts, constants.ts
│   ├── components/
│   │   ├── ui/       — shadcn primitives
│   │   ├── layout/   — app-shell.tsx, sidebar.tsx, header.tsx
│   │   ├── upload/   — file-dropzone.tsx, text-paste-input.tsx, upload-preview.tsx
│   │   ├── match/    — stats-bar.tsx, status-badge.tsx, results-table.tsx, candidate-list.tsx, progress-bar.tsx
│   │   ├── review/   — review-panel.tsx, approve-button.tsx, pick-alternative.tsx, reject-button.tsx
│   │   └── export/   — export-button.tsx
│   └── routes/
│       ├── __root.tsx, login.tsx, not-found.tsx
│       └── _authenticated/
│           ├── index.tsx              — dashboard (upload + submit)
│           ├── requests/index.tsx     — request history
│           ├── requests/$requestId.tsx — results + review (core workflow)
│           └── admin/index.tsx        — catalog import, reindex, metrics
```

### Pages

| Route | Purpose |
|-------|---------|
| `/login` | Username + password → JWT |
| `/` | Main screen: supplier selector, drag-drop CSV / paste text, submit |
| `/requests` | History of batch requests with stats |
| `/requests/:id` | **Core workflow:** stats bar → results table (green/yellow/red) → inline review → export |
| `/admin` | Catalog import, reindex, quality metrics |

### Key UX Decisions
- **Russian UI** throughout
- **Color coding:** auto_match=green, review_needed=yellow, no_match=red
- **One-click approve** for auto_match and review_needed items
- **Inline candidate expansion** — click row to see alternatives with scores and reasons
- **Polling** batch status every 3s (TanStack Query `refetchInterval`)
- **Stats counter:** "342 из 500 найдено автоматически"
- **Supplier selector** persisted to localStorage
- **Export:** CSV/XLSX download of results
- **No global state lib** — TanStack Query for server state, React context for auth + supplier selection only

### API Integration
- `src/api/client.ts`: ky instance with `/api/v1` prefix, JWT interceptor (attach token from localStorage), 401 → redirect to login
- `src/api/types.ts`: TypeScript interfaces matching Pydantic schemas (snake_case — backend does NOT use camelCase alias generator)
- Each domain module exports TanStack Query hooks (`useMatchSync`, `useMatchBatch`, `useMatchRequest`, `useMatchItems`, `useReviewItem`, `useSuppliers`, etc.)

### Build Order
1. Scaffold Vite + React + TypeScript + Tailwind + shadcn/ui
2. Layout (app-shell, sidebar, header) + routing
3. API layer + auth (login page, JWT storage, auth guard)
4. Supplier selector + upload components (dropzone, text paste, preview)
5. Match submission + results page (stats bar, results table, status badges, polling)
6. Review flow (approve, pick alternative, reject — inline in table)
7. Export (CSV/XLSX)
8. Request history page
9. Admin page (catalog import, reindex, metrics)
10. Polish (toasts, loading skeletons, empty states, keyboard shortcuts)

---

## Phase 11: Infrastructure & Deployment

### Server: DigitalOcean Droplet
- **Size:** 8 GB RAM / 4 vCPU / 160 GB SSD (~$48/mo)
- **OS:** Ubuntu 22.04 LTS

### Production Docker Compose (`docker-compose.prod.yml`)

| Service | Image | Exposed Ports |
|---------|-------|---------------|
| `nginx` | Custom (nginx:1.25-alpine + frontend dist + SSL) | 80, 443 |
| `api` | Build from `Dockerfile` | none (internal 8000) |
| `worker` | Same image as api | none |
| `db` | `pgvector/pgvector:pg16` | none (internal only) |
| `redis` | `redis:7-alpine` | none (internal only) |
| `backup` | Custom (alpine + pg_dump + s3cmd) | none |
| `alerter` | Custom (python:3.12-alpine) | none |

All services on internal `matcher-net` bridge network. Only nginx exposed to host.

### New Infrastructure Files

```
infra/
  nginx/
    Dockerfile                 — nginx + frontend dist
    nginx.conf                 — SSL, proxy /api → api:8000, SPA fallback
    nginx-http-only.conf       — Bootstrap for initial certbot
  postgres/
    postgresql.conf            — Tuned for 8GB (shared_buffers=2GB, work_mem=64MB, etc.)
    init.sql                   — CREATE EXTENSION vector, pg_trgm, unaccent
  redis/
    redis.conf                 — maxmemory 256mb, AOF persistence
  backup/
    Dockerfile, backup.sh      — Daily pg_dump to DigitalOcean Spaces, 30-day retention
  alerter/
    Dockerfile, alerter.py     — Health check poller + Telegram notifications
  certbot/
    renew.sh                   — certbot renew + nginx reload (cron every 12h)
```

### Dockerfile Update (multi-stage with frontend)
1. **Stage 1 — Frontend:** node:22-alpine, `npm ci`, `npm run build` → `dist/`
2. **Stage 2 — Python builder:** existing uv builder stage (unchanged)
3. **Stage 3 — Runtime:** python:3.12-slim, copy venv, copy `src/`, `migrations/` (fix from `alembic`), `configs/`; add non-root user

### PostgreSQL Tuning (`infra/postgres/postgresql.conf`)
- `shared_buffers = 2GB`, `effective_cache_size = 6GB`, `work_mem = 64MB`
- `maintenance_work_mem = 512MB`, `max_connections = 100`
- `random_page_cost = 1.1`, `effective_io_concurrency = 200` (SSD)
- `log_min_duration_statement = 500` (log slow queries)

### Security
- UFW: only 22, 80, 443
- SSH key-only auth, fail2ban
- DB and Redis not exposed to host (Docker internal only)
- `.env.production` on server only, never in git
- JWT secret: `openssl rand -hex 32` per deployment
- Rate limiting on match endpoints (simple middleware)
- Non-root Docker user

### Backup
- Daily pg_dump at 03:00 UTC → DigitalOcean Spaces (S3-compatible)
- 30 daily + 12 weekly retention
- Failure alerts to Telegram

### Monitoring (Minimal for Launch)
- Structured JSON logging (stdlib `logging` + custom formatter)
- Docker log rotation (`max-size: 50m`, `max-file: 5`)
- Telegram alerts: service down, worker queue stalled (>100 jobs), high error rate
- Health endpoint checks DB + Redis connectivity

### Deployment Script (`scripts/deploy.sh`)
```
git pull → docker compose build → alembic upgrade head → docker compose up -d → health check → telegram notify
```

### SSL
- Certbot with Let's Encrypt
- Bootstrap: HTTP-only nginx → certbot obtains cert → swap to HTTPS config → reload
- Auto-renewal via cron every 12h

---

## Phase 12: Testing

**Goal:** Comprehensive test coverage before shipping.

### Fix test infrastructure

**Modify `tests/conftest.py`:**
- Shared `db_session` async fixture (currently duplicated across test files)
- `client` fixture with `httpx.AsyncClient` + `ASGITransport`
- `auth_headers` fixture (create test user, return Bearer token)
- `sample_products` fixture (insert a few catalog products)
- `sample_supplier` fixture

### New test files

| File | Tests |
|------|-------|
| `tests/test_api/test_auth_api.py` | Login success/failure, /me endpoint, expired/invalid token |
| `tests/test_api/test_review_api.py` | Accept/correct/reject flows, alias creation, supplier mapping creation, 404 |
| `tests/test_api/test_catalog_api.py` | Import returns 202, reindex returns 202, role requirements |
| `tests/test_api/test_suppliers_api.py` | List suppliers, create mapping, 404 |
| `tests/test_api/test_metrics_api.py` | Quality metrics with/without data, filters |
| `tests/test_worker/test_tasks.py` | batch_match processes items, catalog_import with sample CSV, catalog_reindex |

### Existing tests — update
- Add auth headers to all requests in `test_match_api.py`
- Remove duplicated db_session fixture (use shared conftest)

---

## Phase 13: Final Hardening

| Action | File |
|--------|------|
| Fail startup if `jwt_secret_key == "change-me-in-production"` and not DEBUG | `src/matcher/config.py` |
| Create `.env.production.example` with all required vars documented | `.env.production.example` |
| Populate `README.md` (quick start, architecture, API summary, deployment) | `README.md` |
| Add health check to api service in docker-compose | `docker-compose.prod.yml` |

---

## Execution Order & Dependencies

```
Phase 0  (Cleanup)           ─── no deps
Phase 1  (Repos)             ─── no deps
Phase 2  (Auth)              ─── no deps (parallel with 0, 1)
Phase 3  (App Infrastructure)─── depends on 1, 2
Phase 4  (Catalog endpoints) ─── depends on 1, 3
Phase 5  (Batch match)       ─── depends on 1, 3
Phase 6  (Suppliers)         ─── depends on 1, 2
Phase 7  (Metrics)           ─── depends on 1, 2
Phase 8  (Review refactor)   ─── depends on 1, 2
Phase 9  (Sample data)       ─── depends on 1, 4
Phase 10 (Frontend)          ─── depends on 2, 3 (can start scaffolding earlier)
Phase 11 (Infrastructure)    ─── depends on 10 (for nginx + frontend build)
Phase 12 (Testing)           ─── depends on all backend phases (0-8)
Phase 13 (Hardening)         ─── depends on all above
```

**Parallelization:** Phases 0, 1, 2 can run simultaneously. Phases 6, 7, 8 can run simultaneously. Frontend scaffolding (Phase 10 steps 1-3) can start alongside backend work.

---

## Files Summary

### Delete (Phase 0)
All 17 files in `app/` directory

### Create (34 new files)

**Backend (16 files):**
- `src/matcher/db/repos/{__init__, catalog, supplier, match, metrics, user}.py`
- `src/matcher/auth/{__init__, security, deps}.py`
- `src/matcher/api/v1/auth.py`
- `src/matcher/logging_config.py`
- `src/matcher/api/middleware.py`
- `migrations/versions/xxxx_add_users.py`
- `scripts/create_admin.py`
- `scripts/seed_sample_data.py`
- `scripts/seed_test_queries.py`

**Frontend (~40+ files):** Full React SPA in `frontend/`

**Infrastructure (12 files):**
- `infra/nginx/{Dockerfile, nginx.conf, nginx-http-only.conf}`
- `infra/postgres/{postgresql.conf, init.sql}`
- `infra/redis/redis.conf`
- `infra/backup/{Dockerfile, backup.sh}`
- `infra/alerter/{Dockerfile, alerter.py}`
- `infra/certbot/renew.sh`
- `docker-compose.prod.yml`
- `scripts/deploy.sh`
- `.env.production.example`

**Tests (7 files):**
- `tests/test_api/{test_auth_api, test_review_api, test_catalog_api, test_suppliers_api, test_metrics_api}.py`
- `tests/test_worker/{__init__, test_tasks}.py`

### Modify (18 files)
- `pyproject.toml` — add pyjwt, passlib[bcrypt]
- `Dockerfile` — fix migrations copy, add frontend stage, non-root user
- `docker-compose.yml` — add env vars, health checks
- `src/matcher/main.py` — lifespan (arq pool), CORS, auth router, health checks, middleware
- `src/matcher/config.py` — JWT, CORS, logging settings
- `src/matcher/db/models.py` — add User model
- `src/matcher/db/repos/__init__.py` — re-export (exists but empty)
- `src/matcher/api/deps.py` — add get_arq_pool
- `src/matcher/api/v1/match.py` — use repos, wire arq, add auth
- `src/matcher/api/v1/review.py` — use repos, auth, golden labels
- `src/matcher/api/v1/catalog.py` — implement (replace stubs)
- `src/matcher/api/v1/suppliers.py` — implement (replace stubs)
- `src/matcher/api/v1/metrics.py` — implement (replace stubs)
- `src/matcher/worker/tasks.py` — implement batch_match, catalog_import
- `src/matcher/worker/settings.py` — add startup/shutdown hooks
- `src/matcher/indexing/indexer.py` — accept session_factory param
- `tests/conftest.py` — shared fixtures
- `tests/test_api/test_match_api.py` — add auth, use shared fixtures
- `README.md` — populate

---

## Verification Plan

### Backend Verification
1. `pytest tests/` — all tests pass (unit + integration)
2. Start services: `docker compose up -d`
3. Run migrations: `docker compose exec api alembic upgrade head`
4. Create admin: `docker compose exec api python scripts/create_admin.py`
5. Seed data: `docker compose exec api python scripts/seed_sample_data.py`
6. Trigger reindex: `curl -X POST localhost:8000/api/v1/catalog/reindex -H "Authorization: Bearer <token>"`
7. Test match: `curl -X POST localhost:8000/api/v1/match -H "Authorization: Bearer <token>" -d '{"items":[{"raw_text":"насос grundfos 25-40"}]}'`
8. Test batch: submit batch, poll status until done, verify items have results
9. Test review: approve/correct/reject items, verify golden labels created
10. Verify health: `curl localhost:8000/api/v1/health` returns DB + Redis status

### Frontend Verification
1. `cd frontend && npm run build` — builds without errors
2. Login flow: correct credentials → redirect to dashboard, wrong → error message
3. Upload CSV → preview → submit → redirect to results page
4. Results page: stats bar shows correct counts, status filter tabs work
5. Expand row → see candidates with scores and reasons
6. Approve item → optimistic update, row turns green
7. Pick alternative → item updated
8. Export → CSV/XLSX downloads with correct data
9. Request history → shows all past requests with stats

### Infrastructure Verification
1. `docker compose -f docker-compose.prod.yml up -d` — all services healthy
2. `curl -k https://<domain>/api/v1/health` — returns ok
3. `curl https://<domain>/` — serves frontend SPA
4. Kill api container → Telegram alert received within 2 minutes
5. Restore from backup: `pg_restore` on fresh DB, verify data integrity
6. `scripts/deploy.sh` — git pull + build + migrate + restart succeeds

### End-to-End Smoke Test
1. Login as admin
2. Import sample catalog (seed script or CSV upload via admin)
3. Trigger reindex, wait for completion
4. Select a supplier, paste 20 product names, submit
5. Verify: some auto-matched (green), some need review (yellow), some no match (red)
6. Review 5 yellow items: approve 3, correct 1, reject 1
7. Submit the same 20 items again → corrected/approved items should now auto-match (via supplier mappings)
8. Export results as CSV, verify contents
9. Check quality metrics on admin page
