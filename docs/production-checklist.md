# Production Checklist / Production Чеклист

## English

Use this checklist before exposing a deployment to real users.

### Secrets

- Generate a unique `JWT_SECRET_KEY` with at least 32 random bytes.
- Replace `POSTGRES_PASSWORD` and `REDIS_PASSWORD`.
- Keep `.env.production` outside Git.
- Store hosted provider API keys only when hosted providers are enabled.

### Network and TLS

- Set explicit `CORS_ORIGINS` for the production domain.
- Keep `COOKIE_SECURE=true` behind HTTPS.
- Confirm nginx serves `/health` over HTTP and API traffic over HTTPS.
- Renew certificates with the included certbot scripts or an equivalent process.

### Data

- Run `alembic upgrade head` before app traffic.
- Import and validate the catalog before enabling batch matching.
- Run the backup restore drill in `docs/backup-restore-drill.md`, not only a backup creation check.
- Keep uploaded catalog files on a persistent volume.

### AI Providers

- Use `local` providers for a fully free deployment.
- Build the app image with `USE_LOCAL=true` when local embeddings/rerank run inside the container.
- If using hosted providers, configure rate limits, budgets, and fallback behavior.
- Keep `agentic_resolution_enabled=false` unless web-search behavior is explicitly approved.

### Operations

- Confirm all production services are healthy: nginx, api, worker-match, worker-catalog, db, redis.
- Confirm logs are capped and rotated by Docker.
- Confirm alerts are routed to the expected Telegram chat or replacement alert sink.
- Run dependency audits for backend and frontend before release.
- Run the readiness check:

```bash
uv run python scripts/check_production_readiness.py
```

## Русский

Используйте этот чеклист перед открытием production deployment для реальных пользователей.

### Secrets

- Сгенерируйте уникальный `JWT_SECRET_KEY` минимум из 32 случайных bytes.
- Замените `POSTGRES_PASSWORD` и `REDIS_PASSWORD`.
- Не коммитьте `.env.production` в Git.
- Храните API keys hosted providers только если эти провайдеры включены.

### Network and TLS

- Укажите явные `CORS_ORIGINS` для production domain.
- Используйте `COOKIE_SECURE=true` за HTTPS.
- Проверьте, что nginx отдает `/health` по HTTP и API traffic по HTTPS.
- Настройте renewal сертификатов через included certbot scripts или эквивалентный процесс.

### Data

- Выполните `alembic upgrade head` до приема traffic.
- Импортируйте и провалидируйте catalog до batch matching.
- Проведите restore drill из `docs/backup-restore-drill.md`, а не только проверку создания backup.
- Храните uploaded catalog files на persistent volume.

### AI Providers

- Используйте `local` providers для полностью бесплатного deployment.
- Собирайте app image с `USE_LOCAL=true`, если local embeddings/rerank работают внутри container.
- При hosted providers настройте rate limits, budgets и fallback behavior.
- Оставляйте `agentic_resolution_enabled=false`, пока web-search behavior явно не утвержден.

### Operations

- Проверьте health всех production services: nginx, api, worker-match, worker-catalog, db, redis.
- Убедитесь, что Docker logs ограничены по размеру и количеству файлов.
- Проверьте доставку alerts в нужный Telegram chat или альтернативный alert sink.
- Запустите dependency audits для backend и frontend перед release.
- Запустите readiness check:

```bash
uv run python scripts/check_production_readiness.py
```
