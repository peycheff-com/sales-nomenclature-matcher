# Sales Nomenclature Matcher

Open-source tool for matching customer sales nomenclature against a 1C product catalog.

Инструмент с открытым исходным кодом для сопоставления клиентской номенклатуры со справочником 1C.

## English

### What It Does

Sales Nomenclature Matcher combines deterministic normalization, PostgreSQL lexical search, pgvector semantic search, optional reranking, and scoring rules to classify every incoming item as:

- `auto_match` when confidence is high enough for automatic processing
- `review_needed` when an operator should confirm the candidate
- `no_match` when the catalog has no reliable match

The default configuration is free/local-first. Hosted AI providers are optional.

### Open-Source Status

- License: MIT
- Runtime: self-hosted with Docker Compose
- Default AI mode: local embeddings/rerank/chat-compatible settings
- Optional hosted providers: OpenAI, OpenRouter, Cohere, Together, DashScope, Jina, Google, Yandex, GigaChat, Moonshot
- CI: backend lint, frontend lint/build/typecheck, backend tests, production-compose smoke test

### Architecture

- Backend: Python 3.12, FastAPI, async SQLAlchemy, ARQ
- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Router/Query/Table
- Database: PostgreSQL 16 with pgvector and pg_trgm
- Queue: Redis 7
- Deployment: Docker Compose with nginx, backups, health checks, and alerting

### Matching Pipeline

1. Normalization: Unicode cleanup, Cyrillic/Latin handling, numbers, units, abbreviations, synonyms, packaging, brands, stopwords, tokenization
2. Retrieval: article lookup, PostgreSQL full-text search, trigram search, pgvector semantic search, RRF fusion
3. Reranking: local CrossEncoder by default, hosted providers optional
4. Scoring: weighted feature formula with hard gates
5. Decision: `auto_match >= 0.93`, `review_needed >= 0.75`, `no_match < 0.75`

### Local Development

Requirements:

- Python 3.12
- Node.js 22+
- Docker and Docker Compose
- uv

```bash
docker compose up -d db redis
uv sync --dev
alembic upgrade head
python scripts/create_admin.py
python scripts/seed_sample_data.py
uvicorn matcher.main:app --host 0.0.0.0 --port 8000 --reload
```

In separate terminals:

```bash
arq matcher.worker.settings.WorkerSettings
cd frontend && npm ci && npm run dev
```

The app runs at [http://localhost:5173](http://localhost:5173).

### Free Local AI Mode

For local embeddings and reranking:

```bash
uv sync --extra local --dev
```

For local chat/LLM features, run an OpenAI-compatible Ollama endpoint:

```bash
ollama pull qwen2.5:7b-instruct
ollama serve
```

The application can still operate without LLM features; deterministic retrieval, scoring, and review workflows remain available.

### Tests

```bash
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Coverage gates are enforced for backend and frontend. See [docs/testing.md](docs/testing.md)
for the current thresholds and commands.

### Production

```bash
cp .env.production.example .env.production
# Fill secrets and domain values.
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml exec api python scripts/create_admin.py
```

For local AI inside the production image, build the app image with `USE_LOCAL=true`.

### Documentation

- [Open-source readiness](docs/open-source.md)
- [Testing and coverage](docs/testing.md)
- [Production checklist](docs/production-checklist.md)
- [Backup restore drill](docs/backup-restore-drill.md)
- [Production runbook](docs/deploy_runbook.md)
- [Release process](docs/release.md)
- [Provider matrix](docs/provider_matrix.md)
- [Scoring formula](docs/scoring_v1.md)
- [OpenAPI spec](docs/openapi_v1.yaml)

## Русский

### Назначение

Sales Nomenclature Matcher сопоставляет клиентские позиции продаж со справочником 1C. Система объединяет нормализацию текста, лексический поиск PostgreSQL, семантический поиск pgvector, опциональный реранкинг и правила скоринга.

Результат для каждой позиции:

- `auto_match`: уверенное автоматическое сопоставление
- `review_needed`: требуется проверка оператором
- `no_match`: надежный кандидат не найден

По умолчанию проект настроен на бесплатный локальный режим. Облачные AI-провайдеры необязательны.

### Статус Open Source

- Лицензия: MIT
- Запуск: self-hosted через Docker Compose
- AI по умолчанию: локальные embeddings/rerank/chat-compatible настройки
- Опциональные провайдеры: OpenAI, OpenRouter, Cohere, Together, DashScope, Jina, Google, Yandex, GigaChat, Moonshot
- CI: lint backend, lint/build/typecheck frontend, backend tests, smoke test production compose

### Архитектура

- Backend: Python 3.12, FastAPI, async SQLAlchemy, ARQ
- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Router/Query/Table
- Database: PostgreSQL 16 с pgvector и pg_trgm
- Queue: Redis 7
- Deployment: Docker Compose с nginx, backups, health checks и alerting

### Pipeline Сопоставления

1. Нормализация: Unicode, кириллица/латиница, числа, единицы измерения, сокращения, синонимы, упаковка, бренды, стоп-слова, токенизация
2. Retrieval: артикулы, PostgreSQL full-text, trigram, pgvector, RRF fusion
3. Reranking: локальный CrossEncoder по умолчанию, облачные провайдеры опционально
4. Scoring: взвешенная формула признаков и hard gates
5. Decision: `auto_match >= 0.93`, `review_needed >= 0.75`, `no_match < 0.75`

### Локальная Разработка

Требования:

- Python 3.12
- Node.js 22+
- Docker и Docker Compose
- uv

```bash
docker compose up -d db redis
uv sync --dev
alembic upgrade head
python scripts/create_admin.py
python scripts/seed_sample_data.py
uvicorn matcher.main:app --host 0.0.0.0 --port 8000 --reload
```

В отдельных терминалах:

```bash
arq matcher.worker.settings.WorkerSettings
cd frontend && npm ci && npm run dev
```

Приложение доступно на [http://localhost:5173](http://localhost:5173).

### Бесплатный Локальный AI Режим

Для локальных embeddings и rerank:

```bash
uv sync --extra local --dev
```

Для локальных LLM-функций запустите OpenAI-compatible Ollama endpoint:

```bash
ollama pull qwen2.5:7b-instruct
ollama serve
```

Приложение может работать и без LLM: доступны deterministic retrieval, scoring и review workflows.

### Тесты

```bash
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Coverage gates закреплены для backend и frontend. Текущие thresholds и команды
описаны в [docs/testing.md](docs/testing.md).

### Production

```bash
cp .env.production.example .env.production
# Заполните secrets и domain values.
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml exec api python scripts/create_admin.py
```

Для локального AI внутри production image соберите app image с `USE_LOCAL=true`.

### Документация

- [Open-source readiness](docs/open-source.md)
- [Testing and coverage](docs/testing.md)
- [Production checklist](docs/production-checklist.md)
- [Backup restore drill](docs/backup-restore-drill.md)
- [Production runbook](docs/deploy_runbook.md)
- [Release process](docs/release.md)
- [Provider matrix](docs/provider_matrix.md)
- [Scoring formula](docs/scoring_v1.md)
- [OpenAPI spec](docs/openapi_v1.yaml)
