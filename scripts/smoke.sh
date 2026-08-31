#!/usr/bin/env bash
set -euo pipefail

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' || fail "api /health"

code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health/ready)
[ "$code" = "200" ] || fail "api /health/ready returned $code"

code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000)
[ "$code" = "200" ] || fail "frontend returned $code"

echo "SMOKE OK"
