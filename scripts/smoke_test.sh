#!/usr/bin/env bash
# Post-deploy smoke test
# Usage: ./scripts/smoke_test.sh [BASE_URL]
#
# Checks critical API paths are responding correctly.
# Exits with 0 on success, 1 on failure.

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
FAILURES=0

check() {
  local desc="$1" url="$2" expected_status="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$status" = "$expected_status" ]; then
    echo "  [OK] $desc (HTTP $status)"
  else
    echo "  [FAIL] $desc — expected $expected_status, got $status"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "Smoke test: $BASE_URL"
echo "---"

check "Health endpoint" "$BASE_URL/api/v1/health"
check "Catalog stats" "$BASE_URL/api/v1/catalog/stats" "401"
check "Login page reachable" "$BASE_URL/"

echo "---"
if [ "$FAILURES" -eq 0 ]; then
  echo "All smoke tests passed."
  exit 0
else
  echo "$FAILURES smoke test(s) FAILED."
  exit 1
fi
