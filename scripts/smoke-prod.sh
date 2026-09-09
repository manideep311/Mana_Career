#!/usr/bin/env bash
# Production smoke: the full compose.prod.yml stack, reached through nginx/TLS.
# Self-signed certs -> curl -k. Run after `docker compose -f compose.prod.yml up -d`.
set -euo pipefail

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

base_https="https://localhost"
base_http="http://localhost"

# 1. nginx liveness
curl -fsSk "$base_https/nginx-health" | grep -q "ok" || fail "nginx /nginx-health"

# 2. backend health through nginx
curl -fsSk "$base_https/health" | grep -q '"status":"ok"' || fail "/health via nginx"

# 3. backend readiness through nginx (db + redis + migrations)
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/health/ready")
[ "$code" = "200" ] || fail "/health/ready returned $code"

# 4. API reachable through the /api/ location
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/api/openapi.json")
[ "$code" = "200" ] || fail "/api/openapi.json returned $code"

# 5. frontend (Next.js standalone) served at /
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/")
[ "$code" = "200" ] || fail "frontend / returned $code"

# 6. plain HTTP is redirected to HTTPS
redirect=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$base_http/")
case "$redirect" in
  30[12]\ https://*) : ;;
  *) fail "http:// not redirected to https (got: $redirect)" ;;
esac

echo "SMOKE OK"
