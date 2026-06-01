# Contributing / Участие в проекте

## English

Contributions are welcome. Keep changes focused, explain operational impact,
and include tests for behavioral changes.

### Development

```bash
uv sync --dev
docker compose up -d db redis
PYTHONPATH=src uv run pytest
cd frontend && npm ci && npm run lint && npm run test:coverage && npm run build
```

Use `uv sync --extra local --dev` when working on local embeddings or reranking.

### Pull Requests

- Explain user-facing behavior, API changes, migrations, or operational impact.
- Add or update English and Russian documentation when behavior changes.
- Add backend tests for Python changes.
- Add frontend tests for UI, API-client, hook, and route changes.
- Keep coverage gates passing: backend 100%; frontend 100% statements, lines,
  functions, and the configured branch threshold.
- Keep secrets out of commits. `.env` and `.env.*` are ignored except
  `.env.production.example`.
- Update `CHANGELOG.md` for notable user-facing, API, deployment, or security
  changes.

### Code Style

- Python: Ruff, Python 3.12, async SQLAlchemy for DB work.
- TypeScript: strict mode, ESLint, React hooks rules.
- API routes stay under `/api/v1/`.

### Reporting Issues

Include reproduction steps, expected behavior, actual behavior, logs, and
environment details.

## Русский

Contributions приветствуются. Держите изменения сфокусированными, описывайте
operational impact и добавляйте tests для изменений поведения.

### Разработка

```bash
uv sync --dev
docker compose up -d db redis
PYTHONPATH=src uv run pytest
cd frontend && npm ci && npm run lint && npm run test:coverage && npm run build
```

Используйте `uv sync --extra local --dev` для работы с локальными embeddings
или reranking.

### Pull Requests

- Опишите user-facing behavior, API changes, migrations или operational impact.
- Обновляйте English и Russian документацию, если меняется поведение.
- Добавляйте backend tests для Python changes.
- Добавляйте frontend tests для UI, API-client, hook и route changes.
- Сохраняйте coverage gates зелеными: backend 100%; frontend 100% statements,
  lines, functions и настроенный branch threshold.
- Не коммитьте secrets. `.env` и `.env.*` игнорируются, кроме
  `.env.production.example`.
- Обновляйте `CHANGELOG.md` для значимых user-facing, API, deployment или
  security changes.

### Code Style

- Python: Ruff, Python 3.12, async SQLAlchemy для DB.
- TypeScript: strict mode, ESLint, React hooks rules.
- API routes остаются в `/api/v1/`.

### Issues

Укажите reproduction steps, expected behavior, actual behavior, logs и детали
окружения.
