#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -p 1c -f docker-compose.prod.yml"
APP_IMAGE="${APP_IMAGE:?Set APP_IMAGE to a GHCR app image tag}"
NGINX_IMAGE="${NGINX_IMAGE:?Set NGINX_IMAGE to a GHCR nginx image tag}"
BASE_URL="${BASE_URL:-https://localhost}"
export APP_IMAGE
export NGINX_IMAGE

if [[ -n "${GHCR_TOKEN:-}" && -n "${GHCR_USER:-}" ]]; then
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
fi

echo "=== Pulling immutable images ==="
$COMPOSE pull api worker-match worker-catalog nginx

echo "=== Starting stateful dependencies ==="
$COMPOSE up -d db redis

echo "=== Running migrations ==="
$COMPOSE run --rm api alembic upgrade head

echo "=== Starting application services ==="
$COMPOSE up -d --remove-orphans backup alerter api worker-match worker-catalog nginx

echo "=== Waiting for health checks ==="
sleep 15
./scripts/smoke_test.sh "${BASE_URL}" --require-ready
echo "=== Deploy successful ==="
