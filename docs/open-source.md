# Open-Source Readiness / Готовность к Open Source

## English

This repository is intended to be usable as a fully self-hosted, free, open-source project.

Current status:

- MIT license is included.
- Local/free provider mode is the default.
- Hosted AI providers are optional.
- Secrets are excluded by `.gitignore`.
- CI runs backend lint/tests, frontend lint/build/coverage checks, and production-compose smoke tests.
- Backend coverage is enforced at 100% through `pyproject.toml`.
- Frontend coverage is enforced through Vitest at 100% statements, 100% lines, 100% functions, and 100% branches.
- OSV Scanner runs dependency vulnerability scans for pushes, pull requests, weekly schedule, and manual dispatch.
- The SBOM workflow generates an SPDX JSON SBOM artifact on `main`, version tags, and manual dispatch.
- Production deployment uses Docker Compose, health checks, nginx, Redis, PostgreSQL, backups, and alerting.
- A production checklist and backup restore drill are maintained in `docs/production-checklist.md` and `docs/backup-restore-drill.md`.

Release operators should execute the backup restore drill before opening a specific deployment to real users.

## Русский

Репозиторий рассчитан на self-hosted, бесплатное и полностью open-source использование.

Текущий статус:

- Добавлена лицензия MIT.
- Локальный/бесплатный provider mode используется по умолчанию.
- Облачные AI-провайдеры опциональны.
- Secrets исключены через `.gitignore`.
- CI запускает backend lint/tests, frontend lint/build/coverage checks и smoke tests для production compose.
- Backend coverage закреплен на 100% через `pyproject.toml`.
- Frontend coverage закреплен через Vitest на уровне 100% statements, 100% lines, 100% functions и 100% branches.
- OSV Scanner запускает dependency vulnerability scans для push, pull request, weekly schedule и manual dispatch.
- SBOM workflow генерирует SPDX JSON SBOM artifact на `main`, version tags и manual dispatch.
- Production deployment использует Docker Compose, health checks, nginx, Redis, PostgreSQL, backups и alerting.
- Production checklist и backup restore drill поддерживаются в `docs/production-checklist.md` и `docs/backup-restore-drill.md`.

Перед открытием конкретного deployment для реальных пользователей операторы должны выполнить backup restore drill.
