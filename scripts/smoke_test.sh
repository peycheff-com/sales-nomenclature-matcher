#!/usr/bin/env bash
# Post-deploy smoke test
# Usage: ./scripts/smoke_test.sh [BASE_URL] [--require-ready]
#
# Checks critical API paths are responding correctly.
# Exits with 0 on success, 1 on failure.

set -euo pipefail

BASE_URL="${1:-http://localhost}"
REQUIRE_READY="${2:-}"
FAILURES=0
CURL_OPTS=(--max-time 10)

if [[ "${BASE_URL}" == https://* ]]; then
  CURL_OPTS+=(-k)
fi

check() {
  local desc="$1" url="$2" expected_status="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "${CURL_OPTS[@]}" "$url" 2>/dev/null || echo "000")
  if [ "$status" = "$expected_status" ]; then
    echo "  [OK] $desc (HTTP $status)"
  else
    echo "  [FAIL] $desc — expected $expected_status, got $status"
    FAILURES=$((FAILURES + 1))
  fi
}

check_json_field() {
  local desc="$1" url="$2" field="$3" expected="$4"
  local body actual
  body=$(curl -s "${CURL_OPTS[@]}" "$url" 2>/dev/null || true)
  actual=$(printf "%s" "$body" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get(sys.argv[1], ""))' "$field" 2>/dev/null || true)
  if [ "$actual" = "$expected" ]; then
    echo "  [OK] $desc ($field=$actual)"
  else
    echo "  [FAIL] $desc — expected $field=$expected, got $actual"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "Smoke test: $BASE_URL"
echo "---"

check "Nginx health" "$BASE_URL/health"
check "API live health" "$BASE_URL/api/v1/health/live"
check "API readiness endpoint" "$BASE_URL/api/v1/health"
check_json_field "API readiness payload" "$BASE_URL/api/v1/health" "version" "0.1.0"
check "Catalog stats auth guard" "$BASE_URL/api/v1/catalog/stats" "401"
check "SPA root reachable" "$BASE_URL/"

if [ "$REQUIRE_READY" = "--require-ready" ]; then
  check_json_field "API readiness status" "$BASE_URL/api/v1/health" "status" "ok"
fi

echo "---"
if [ "$FAILURES" -eq 0 ]; then
  echo "All smoke tests passed."
  exit 0
else
  echo "$FAILURES smoke test(s) FAILED."
  exit 1
fi
