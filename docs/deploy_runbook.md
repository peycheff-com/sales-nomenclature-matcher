# Deployment Runbook

## Pre-deploy

1. **Backup database:**
   ```bash
   docker compose -f docker-compose.prod.yml exec db pg_dump -U matcher matcher > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Pull latest code:**
   ```bash
   git pull origin main
   ```

3. **Review migrations:**
   ```bash
   alembic history --verbose
   ```

## Deploy

1. **Build images:**
   ```bash
   docker compose -f docker-compose.prod.yml build
   ```

2. **Run migrations:**
   ```bash
   docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
   ```

3. **Restart services:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. **Run smoke test:**
   ```bash
   ./scripts/smoke_test.sh https://your-domain.com
   ```

## Post-deploy

1. Check health: `GET /api/v1/health`
2. Check logs: `docker compose -f docker-compose.prod.yml logs -f api worker`
3. Verify catalog stats: `GET /api/v1/catalog/stats`

## Rollback

1. **Stop services:**
   ```bash
   docker compose -f docker-compose.prod.yml stop api worker
   ```

2. **Rollback migration (if needed):**
   ```bash
   docker compose -f docker-compose.prod.yml run --rm api alembic downgrade -1
   ```

3. **Restore previous image:**
   ```bash
   git checkout <previous-tag>
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml up -d
   ```

4. **Restore database (if needed):**
   ```bash
   cat backup_YYYYMMDD.sql | docker compose -f docker-compose.prod.yml exec -T db psql -U matcher matcher
   ```

## Index Rollback

To roll back to a previous search index version:

```bash
curl -X POST https://your-domain.com/api/v1/catalog/rollback \
  -H "Content-Type: application/json" \
  -d '{"index_version_id": "version_id_here"}'
```

List available versions: `GET /api/v1/catalog/index-versions`
