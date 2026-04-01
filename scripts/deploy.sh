#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="/opt/matcher"
REPO_DIR="$DEPLOY_DIR/repo"
COMPOSE="docker compose -f docker-compose.prod.yml"

cd "$REPO_DIR"

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Building images ==="
$COMPOSE build

echo "=== Running migrations ==="
$COMPOSE run --rm api alembic upgrade head

echo "=== Starting services ==="
$COMPOSE up -d --remove-orphans

echo "=== Waiting for health check ==="
sleep 10
if curl -sf http://localhost/api/v1/health > /dev/null 2>&1; then
    echo "=== Deploy successful ==="
else
    echo "=== HEALTH CHECK FAILED ==="
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=Deploy FAILED: health check failed at $(date)" > /dev/null 2>&1
    fi
    exit 1
fi
