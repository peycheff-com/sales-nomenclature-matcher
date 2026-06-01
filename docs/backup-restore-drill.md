# Backup Restore Drill / Проверка восстановления backups

## English

Run this drill before a first production launch and then on a recurring operations schedule. The goal is to prove that backups can restore a working PostgreSQL database, not only that backup files are created.

### Frequency

- Before opening a new production deployment to operators.
- After changing backup storage, database version, or migration strategy.
- At least monthly for active installations.

### Prerequisites

- A recent backup file from the `backup` service or an equivalent `pg_dump` output.
- Access to the production `.env.production` values.
- A disposable restore target. Do not restore into the live production database during a drill.

### Drill

1. Create a timestamped backup if one is not already available:

```bash
docker compose -p 1c -f docker-compose.prod.yml exec -T db pg_dump -U matcher matcher > backup_$(date +%Y%m%d_%H%M%S).sql
```

2. Start a disposable PostgreSQL container on an isolated Docker volume:

```bash
docker volume create matcher_restore_drill
docker run --rm -d --name matcher-restore-drill \
  -e POSTGRES_USER=matcher \
  -e POSTGRES_PASSWORD=matcher \
  -e POSTGRES_DB=matcher \
  -v matcher_restore_drill:/var/lib/postgresql/data \
  postgres:16
```

3. Restore the backup into the disposable database:

```bash
cat backup_YYYYMMDD_HHMMSS.sql | docker exec -i matcher-restore-drill psql -U matcher matcher
```

4. Verify that core tables and row counts are present:

```bash
docker exec -i matcher-restore-drill psql -U matcher matcher -c "\dt"
docker exec -i matcher-restore-drill psql -U matcher matcher -c "select count(*) from catalog_products;"
docker exec -i matcher-restore-drill psql -U matcher matcher -c "select count(*) from match_requests;"
```

5. Record the result in the operations log:

```text
date:
backup file:
restore target:
schema check:
catalog_products count:
match_requests count:
operator:
notes:
```

6. Remove the disposable restore target:

```bash
docker rm -f matcher-restore-drill
docker volume rm matcher_restore_drill
```

## Русский

Проводите этот drill перед первым production launch и затем регулярно по операционному расписанию. Цель - доказать, что backup реально восстанавливает рабочую PostgreSQL database, а не только создается как файл.

### Периодичность

- Перед открытием нового production deployment для операторов.
- После изменения backup storage, версии database или стратегии migrations.
- Минимум раз в месяц для активных инсталляций.

### Требования

- Свежий backup file от `backup` service или эквивалентный `pg_dump` output.
- Доступ к production значениям `.env.production`.
- Одноразовый restore target. Не восстанавливайте drill backup в live production database.

### Drill

1. Создайте timestamped backup, если готового backup еще нет:

```bash
docker compose -p 1c -f docker-compose.prod.yml exec -T db pg_dump -U matcher matcher > backup_$(date +%Y%m%d_%H%M%S).sql
```

2. Запустите одноразовый PostgreSQL container на изолированном Docker volume:

```bash
docker volume create matcher_restore_drill
docker run --rm -d --name matcher-restore-drill \
  -e POSTGRES_USER=matcher \
  -e POSTGRES_PASSWORD=matcher \
  -e POSTGRES_DB=matcher \
  -v matcher_restore_drill:/var/lib/postgresql/data \
  postgres:16
```

3. Восстановите backup в одноразовую database:

```bash
cat backup_YYYYMMDD_HHMMSS.sql | docker exec -i matcher-restore-drill psql -U matcher matcher
```

4. Проверьте наличие core tables и row counts:

```bash
docker exec -i matcher-restore-drill psql -U matcher matcher -c "\dt"
docker exec -i matcher-restore-drill psql -U matcher matcher -c "select count(*) from catalog_products;"
docker exec -i matcher-restore-drill psql -U matcher matcher -c "select count(*) from match_requests;"
```

5. Зафиксируйте результат в operations log:

```text
date:
backup file:
restore target:
schema check:
catalog_products count:
match_requests count:
operator:
notes:
```

6. Удалите одноразовый restore target:

```bash
docker rm -f matcher-restore-drill
docker volume rm matcher_restore_drill
```
