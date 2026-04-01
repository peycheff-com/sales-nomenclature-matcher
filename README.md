# Sales Nomenclature Matcher

Инструмент автоматического сопоставления номенклатуры клиентов со справочником 1С.

## Архитектура

- **Backend:** Python 3.12, FastAPI, SQLAlchemy async, ARQ (Redis)
- **Frontend:** React 19, TypeScript, Vite, shadcn/ui, TanStack
- **Database:** PostgreSQL 16 + pgvector + pg_trgm
- **Queue:** Redis 7
- **Deployment:** Docker Compose, DigitalOcean

## Алгоритм сопоставления

Каскадный pipeline:
1. Нормализация текста (7 этапов: unicode, кириллица/латиница, числа, единицы, бренды, стоп-слова, токенизация)
2. Гибридный поиск (точный + лексический + семантический + RRF-фьюжен)
3. Реранкинг (Cohere / LLM / fallback)
4. Скоринг (15 признаков, взвешенная формула)
5. Решение (auto_match >= 0.93 / review_needed >= 0.75 / no_match)

## Быстрый старт (разработка)

### Требования
- Python 3.12
- Node.js 22+
- Docker и Docker Compose
- uv (Python package manager)

### Запуск

    # Поднять PostgreSQL + Redis
    docker compose up -d db redis

    # Установить зависимости
    uv sync

    # Применить миграции
    alembic upgrade head

    # Создать админа
    python scripts/create_admin.py

    # Загрузить тестовые данные
    python scripts/seed_sample_data.py

    # Запустить API
    uvicorn matcher.main:app --host 0.0.0.0 --port 8000 --reload

    # В отдельном терминале — запустить worker
    arq matcher.worker.settings.WorkerSettings

    # В отдельном терминале — запустить frontend
    cd frontend && npm run dev

Приложение доступно на http://localhost:5173

## API

| Endpoint | Описание |
|----------|----------|
| POST /api/v1/auth/login | Авторизация (JWT) |
| POST /api/v1/match | Синхронное сопоставление |
| POST /api/v1/match/batch | Асинхронное пакетное сопоставление |
| GET /api/v1/match/requests/{id} | Статус запроса |
| GET /api/v1/match/requests/{id}/items | Результаты (пагинация) |
| POST /api/v1/review/items/{id} | Подтвердить/исправить/отклонить |
| GET /api/v1/suppliers | Список поставщиков |
| POST /api/v1/catalog/import | Импорт каталога |
| POST /api/v1/catalog/reindex | Переиндексация |
| GET /api/v1/metrics/quality | Метрики качества |
| GET /api/v1/health | Проверка здоровья |

## Деплой (продакшн)

    # На сервере (DigitalOcean Droplet 8GB RAM)
    cp .env.production.example .env.production
    # Заполнить реальные значения

    docker compose -f docker-compose.prod.yml up -d
    docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
    docker compose -f docker-compose.prod.yml exec api python scripts/create_admin.py

## Тесты

    pytest tests/ -v

## Структура проекта

    src/matcher/          # Backend
      api/v1/             # API endpoints
      auth/               # JWT authentication
      db/                 # Models, repos, engine
      pipeline/           # Matching pipeline (scoring, decisions, explanations)
      normalization/      # Text normalization (7 stages)
      indexing/            # Hybrid search + embeddings
      ingestion/           # CSV/XLSX import
      worker/              # ARQ background tasks
    frontend/              # React SPA
    infra/                 # Production config (nginx, postgres, redis, backup, alerter)
    migrations/            # Alembic database migrations
    configs/               # Normalization rules (YAML)
    scripts/               # CLI utilities
    tests/                 # Test suite
    docs/                  # OpenAPI spec, DDL, scoring formula
