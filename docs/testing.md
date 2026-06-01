# Testing and Coverage / Тестирование и Coverage

## English

Run the full backend test suite:

```bash
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run test:coverage
npm run build
npm audit --audit-level=moderate
```

Coverage gates:

- Backend: `pyproject.toml` enforces `--cov-fail-under=100` for the `matcher`
  package.
- Frontend: `vite.config.ts` enforces 100% statements, 100% lines, 100%
  functions, and 100% branches with V8 coverage.

Both backend and frontend coverage gates are at 100% without excluding
production code from the measured application surface.

Recommended coverage sequence:

1. API route edge cases and auth failures
2. Repository methods with isolated database fixtures
3. Ingestion parser and 1C adapter fixtures
4. Indexing and embedding provider fallbacks
5. Worker retry, cancellation, and recovery paths
6. Frontend component and route tests
7. End-to-end smoke scenarios against Docker Compose

## Русский

Полный backend test suite:

```bash
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run test:coverage
npm run build
npm audit --audit-level=moderate
```

Coverage gates:

- Backend: `pyproject.toml` закрепляет `--cov-fail-under=100` для package
  `matcher`.
- Frontend: `vite.config.ts` закрепляет 100% statements, 100% lines, 100%
  functions и 100% branches через V8 coverage.

Backend и frontend coverage gates установлены на 100% без исключения
production code из измеряемой поверхности приложения.

Рекомендуемый порядок:

1. Edge cases и auth failures в API routes
2. Repository methods с изолированными database fixtures
3. Ingestion parser и fixtures для 1C adapter
4. Indexing и fallback paths embedding providers
5. Worker retry, cancellation и recovery paths
6. Frontend component и route tests
7. End-to-end smoke scenarios через Docker Compose
