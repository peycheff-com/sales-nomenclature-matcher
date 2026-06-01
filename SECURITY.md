# Security Policy / Политика безопасности

## English

### Supported Versions

Security fixes target the `main` branch until versioned releases are introduced.

### Reporting a Vulnerability

Please do not open a public issue for exploitable vulnerabilities. Report privately to:

- Email: mindburnlabs@gmail.com

Include the affected component, reproduction steps, impact, and any suggested fix. You should receive an initial response within 7 days.

### Production Security Checklist

- Generate a unique `JWT_SECRET_KEY` of at least 32 bytes.
- Set explicit `CORS_ORIGINS`; never use `*` in production.
- Keep `LOG_LEVEL=INFO` or stricter in production.
- Set `COOKIE_SECURE=true` behind HTTPS.
- Use strong PostgreSQL and Redis passwords.
- Keep `.env.production` outside version control.
- Run `docker compose -f docker-compose.prod.yml ps` and health checks after deploy.

## Русский

### Поддерживаемые версии

Security fixes поставляются в ветку `main` до появления версионированных релизов.

### Сообщение об уязвимости

Не открывайте публичный issue для exploitable vulnerabilities. Сообщайте приватно:

- Email: mindburnlabs@gmail.com

Укажите затронутый компонент, шаги воспроизведения, impact и возможный fix. Первичный ответ ожидается в течение 7 дней.

### Production Security Checklist

- Сгенерируйте уникальный `JWT_SECRET_KEY` минимум из 32 bytes.
- Укажите явные `CORS_ORIGINS`; не используйте `*` в production.
- Держите `LOG_LEVEL=INFO` или строже в production.
- Используйте `COOKIE_SECURE=true` за HTTPS.
- Используйте сильные passwords для PostgreSQL и Redis.
- Не храните `.env.production` в version control.
- После deploy выполните `docker compose -f docker-compose.prod.yml ps` и health checks.
