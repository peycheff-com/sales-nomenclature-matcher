# Deployment Runbook / Deployment Runbook

## English

### Pre-deploy

1. **Verify CI for the exact release commit:**
   - backend lint green
   - frontend lint/type/build green
   - backend tests green
   - prod-compose smoke green

2. **Backup database:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml exec db pg_dump -U matcher matcher > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

3. **Pull deployment manifests only:**
   ```bash
   git pull origin main
   ```

4. **Review migrations:**
   ```bash
   alembic history --verbose
   ```

5. **Harden the host firewall if not already applied:**
   ```bash
   sudo ./infra/scripts/harden_host.sh
   ```

### Deploy

1. **Export immutable image tags:**
   ```bash
   export APP_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-app:<commit-sha>
   export NGINX_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-nginx:<commit-sha>
   ```

2. **Login to GHCR (if needed):**
   ```bash
   echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
   ```

3. **Link the production env file into the deploy working directory:**
   ```bash
   ln -sf /opt/1C/.env.production .env.production
   ```

4. **Pull the pinned images and start stateful services:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml pull api worker-match worker-catalog nginx
   docker compose -p 1c -f docker-compose.prod.yml up -d db redis
   ```

5. **Run migrations:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml run --rm api alembic upgrade head
   ```

6. **Start the application stack:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml up -d --remove-orphans backup alerter api worker-match worker-catalog nginx
   ```

7. **Run smoke test:**
   ```bash
   ./scripts/smoke_test.sh https://your-domain.com --require-ready
   ```

### Bootstrap

1. **Load the production catalog, build embeddings, create baseline suppliers, save the initial quality report:**
   ```bash
   python scripts/bootstrap_production.py \
     --catalog-file /path/to/master-catalog.xlsx \
     --supplier "Supplier A" \
     --supplier "Supplier B"
   ```

2. **Re-run the smoke test after bootstrap:**
   ```bash
   ./scripts/smoke_test.sh https://your-domain.com --require-ready
   ```

### Launch Rehearsal

1. Run a real 50-row supplier workbook through the dashboard and confirm p95 under 20 seconds.
2. Run a real 200-row supplier workbook and confirm p95 under 60 seconds.
3. Confirm `/api/v1/health` returns `status=ok` with `db`, `redis`, `providers`, `catalog`, and `index` all green.
4. Confirm `GET /api/v1/catalog/stats` shows non-zero catalog and 100% embedding coverage.
5. Confirm the golden-set quality gate is at or above the baseline.
6. Force one controlled API failure and verify the alerter reports the failing target.
7. Run one backup-and-restore drill before opening access to operators.

### Post-deploy

1. Check liveness: `GET /api/v1/health/live`
2. Check readiness: `GET /api/v1/health`
3. Check logs: `docker compose -p 1c -f docker-compose.prod.yml logs -f api worker-match worker-catalog nginx`
4. Verify catalog stats: `GET /api/v1/catalog/stats`
5. Verify ARQ health:
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml exec worker-match arq --check matcher.worker.settings.MatchWorkerSettings
   docker compose -p 1c -f docker-compose.prod.yml exec worker-catalog arq --check matcher.worker.settings.CatalogWorkerSettings
   ```

### Rollback

1. **Pin the previous known-good images:**
   ```bash
   export APP_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-app:<previous-commit-sha>
   export NGINX_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-nginx:<previous-commit-sha>
   ```

2. **Rollback migration (if needed):**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml run --rm api alembic downgrade -1
   ```

3. **Restart the stack on the pinned images:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml pull api worker-match worker-catalog nginx
   docker compose -p 1c -f docker-compose.prod.yml up -d --remove-orphans backup alerter api worker-match worker-catalog nginx
   ```

4. **Restore database (if needed):**
   ```bash
   cat backup_YYYYMMDD.sql | docker compose -p 1c -f docker-compose.prod.yml exec -T db psql -U matcher matcher
   ```

### Index Rollback

To roll back to a previous search index version:

```bash
curl -X POST https://your-domain.com/api/v1/catalog/rollback \
  -H "Content-Type: application/json" \
  -d '{"index_version_id": "version_id_here"}'
```

List available versions: `GET /api/v1/catalog/index-versions`

## Русский

### Pre-deploy

1. **Проверьте CI для точного release commit:**
   - backend lint green
   - frontend lint/type/build green
   - backend tests green
   - prod-compose smoke green

2. **Сделайте backup database:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml exec db pg_dump -U matcher matcher > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

3. **Подтяните только deployment manifests:**
   ```bash
   git pull origin main
   ```

4. **Проверьте migrations:**
   ```bash
   alembic history --verbose
   ```

5. **Укрепите host firewall, если это еще не сделано:**
   ```bash
   sudo ./infra/scripts/harden_host.sh
   ```

### Deploy

1. **Экспортируйте immutable image tags:**
   ```bash
   export APP_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-app:<commit-sha>
   export NGINX_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-nginx:<commit-sha>
   ```

2. **Войдите в GHCR при необходимости:**
   ```bash
   echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
   ```

3. **Свяжите production env file с deploy working directory:**
   ```bash
   ln -sf /opt/1C/.env.production .env.production
   ```

4. **Загрузите pinned images и запустите stateful services:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml pull api worker-match worker-catalog nginx
   docker compose -p 1c -f docker-compose.prod.yml up -d db redis
   ```

5. **Запустите migrations:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml run --rm api alembic upgrade head
   ```

6. **Запустите application stack:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml up -d --remove-orphans backup alerter api worker-match worker-catalog nginx
   ```

7. **Запустите smoke test:**
   ```bash
   ./scripts/smoke_test.sh https://your-domain.com --require-ready
   ```

### Bootstrap

1. **Загрузите production catalog, постройте embeddings, создайте baseline suppliers и сохраните initial quality report:**
   ```bash
   python scripts/bootstrap_production.py \
     --catalog-file /path/to/master-catalog.xlsx \
     --supplier "Supplier A" \
     --supplier "Supplier B"
   ```

2. **Повторите smoke test после bootstrap:**
   ```bash
   ./scripts/smoke_test.sh https://your-domain.com --require-ready
   ```

### Launch Rehearsal

1. Прогоните реальный 50-row supplier workbook через dashboard и подтвердите p95 under 20 seconds.
2. Прогоните реальный 200-row supplier workbook и подтвердите p95 under 60 seconds.
3. Проверьте, что `/api/v1/health` возвращает `status=ok`, а `db`, `redis`, `providers`, `catalog`, `index` green.
4. Проверьте, что `GET /api/v1/catalog/stats` показывает non-zero catalog и 100% embedding coverage.
5. Проверьте, что golden-set quality gate не ниже baseline.
6. Сымитируйте один controlled API failure и убедитесь, что alerter сообщает failing target.
7. Выполните backup-and-restore drill перед открытием доступа операторам.

### Post-deploy

1. Проверьте liveness: `GET /api/v1/health/live`
2. Проверьте readiness: `GET /api/v1/health`
3. Проверьте logs: `docker compose -p 1c -f docker-compose.prod.yml logs -f api worker-match worker-catalog nginx`
4. Проверьте catalog stats: `GET /api/v1/catalog/stats`
5. Проверьте ARQ health:
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml exec worker-match arq --check matcher.worker.settings.MatchWorkerSettings
   docker compose -p 1c -f docker-compose.prod.yml exec worker-catalog arq --check matcher.worker.settings.CatalogWorkerSettings
   ```

### Rollback

1. **Закрепите предыдущие known-good images:**
   ```bash
   export APP_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-app:<previous-commit-sha>
   export NGINX_IMAGE=ghcr.io/<owner>/sales-nomenclature-matcher-nginx:<previous-commit-sha>
   ```

2. **Откатите migration при необходимости:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml run --rm api alembic downgrade -1
   ```

3. **Перезапустите stack на pinned images:**
   ```bash
   docker compose -p 1c -f docker-compose.prod.yml pull api worker-match worker-catalog nginx
   docker compose -p 1c -f docker-compose.prod.yml up -d --remove-orphans backup alerter api worker-match worker-catalog nginx
   ```

4. **Восстановите database при необходимости:**
   ```bash
   cat backup_YYYYMMDD.sql | docker compose -p 1c -f docker-compose.prod.yml exec -T db psql -U matcher matcher
   ```

### Index Rollback

Откат search index на предыдущую версию:

```bash
curl -X POST https://your-domain.com/api/v1/catalog/rollback \
  -H "Content-Type: application/json" \
  -d '{"index_version_id": "version_id_here"}'
```

Список доступных версий: `GET /api/v1/catalog/index-versions`
