# Release Process / Процесс релиза

## English

This project is not yet publishing versioned releases. Until the first release,
all release notes are accumulated in `CHANGELOG.md` under `Unreleased`.

### Versioning

- Use semantic versioning: `MAJOR.MINOR.PATCH`.
- Increment `PATCH` for bug fixes and documentation corrections.
- Increment `MINOR` for backward-compatible features or provider additions.
- Increment `MAJOR` for incompatible API, deployment, data model, or workflow
  changes.

### Release Checklist

1. Move relevant `CHANGELOG.md` entries from `Unreleased` into the target
   version section with the release date.
2. Confirm local/free mode still works without hosted provider keys.
3. Run backend checks:

```bash
uv run ruff check .
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
PYTHONPATH=src uv run python scripts/check_production_readiness.py
```

4. Run frontend checks:

```bash
cd frontend
npm run lint
npm run test:coverage
npm run build
npm audit --audit-level=moderate
```

5. Run the production Docker Compose smoke path from CI or an equivalent
   staging environment.
6. Confirm English and Russian documentation has been updated for user-facing,
   API, deployment, security, or operational changes.
7. Create a signed Git tag when maintainers are ready to publish:

```bash
git tag -s vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

## Русский

Проект пока не публикует версионированные релизы. До первого релиза все release
notes накапливаются в `CHANGELOG.md` в секции `Unreleased`.

### Версионирование

- Используйте semantic versioning: `MAJOR.MINOR.PATCH`.
- Увеличивайте `PATCH` для bug fixes и исправлений документации.
- Увеличивайте `MINOR` для backward-compatible features или добавления
  providers.
- Увеличивайте `MAJOR` для несовместимых изменений API, deployment, data model
  или workflow.

### Release Checklist

1. Перенесите нужные записи `CHANGELOG.md` из `Unreleased` в секцию целевой
   версии с датой релиза.
2. Проверьте, что local/free mode работает без ключей hosted providers.
3. Запустите backend checks:

```bash
uv run ruff check .
PYTHONPATH=src uv run pytest --cov=matcher --cov-report=term-missing --cov-report=xml
PYTHONPATH=src uv run python scripts/check_production_readiness.py
```

4. Запустите frontend checks:

```bash
cd frontend
npm run lint
npm run test:coverage
npm run build
npm audit --audit-level=moderate
```

5. Запустите production Docker Compose smoke path из CI или эквивалентную
   staging-проверку.
6. Убедитесь, что English и Russian документация обновлены для user-facing,
   API, deployment, security или operational changes.
7. Создайте signed Git tag, когда maintainers готовы публиковать релиз:

```bash
git tag -s vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```
