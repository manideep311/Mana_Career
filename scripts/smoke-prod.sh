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
curl -fsSk "$base_https/api/v1/meta" | grep -q '"demo_mode"' || fail "/api/v1/meta via nginx"

# 4b. The API schema is not published in production (nginx never routed /docs
#     to the API; the schema was reachable under /api/)
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/api/openapi.json")
[ "$code" = "404" ] || fail "/api/openapi.json should be 404 in production (got $code)"

# 5. frontend (Next.js standalone) served at /
code=$(curl -s -o /dev/null -w '%{http_code}' -k "$base_https/")
[ "$code" = "200" ] || fail "frontend / returned $code"

# 6. plain HTTP is redirected to HTTPS
redirect=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$base_http/")
case "$redirect" in
  30[12]\ https://*) : ;;
  *) fail "http:// not redirected to https (got: $redirect)" ;;
esac

# Keep the upload/restart exercise opt-in because it creates persistent test
# data. CI enables this only for its disposable stack.
if [ "${SMOKE_UPLOAD_PERSISTENCE:-0}" != "1" ]; then
  echo "SMOKE OK (HTTP checks; upload persistence skipped)"
  exit 0
fi

# 7. Exercise the shared API/worker file store with a synthetic PDF. Keep the
# persisted upload: production smoke runs must not remove application data.
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
python3 - "$tmpdir/smoke.pdf" <<'PY'
import sys
from pathlib import Path

objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>",
    b"<< /Length 0 >>\nstream\n\nendstream",
]
pdf = bytearray(b"%PDF-1.4\n")
offsets = [0]
for index, body in enumerate(objects, 1):
    offsets.append(len(pdf))
    pdf.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
xref = len(pdf)
pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]:
    pdf.extend(f"{offset:010d} 00000 n \n".encode())
pdf.extend(
    f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
)
Path(sys.argv[1]).write_bytes(pdf)
PY

api_uid=$(docker compose -f compose.prod.yml exec -T api id -u)
worker_uid=$(docker compose -f compose.prod.yml exec -T worker id -u)
[ "$api_uid" = "10001" ] || fail "api uid is $api_uid, expected 10001"
[ "$worker_uid" = "10001" ] || fail "worker uid is $worker_uid, expected 10001"
docker compose -f compose.prod.yml exec -T api sh -c 'test -w /app/var/files' || fail "api file store is not writable"
docker compose -f compose.prod.yml exec -T worker sh -c 'test -w /app/var/files' || fail "worker file store is not writable"

stamp=$(date +%s)-${RANDOM}
email="smoke-${stamp}@example.invalid"
password="smoke-only-password-${stamp}"
curl -fsSk "$base_https/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$password\",\"full_name\":\"Production Smoke\"}" \
  > "$tmpdir/register.json" || fail "synthetic smoke user registration"
token=$(jq -er '.access_token' "$tmpdir/register.json") || fail "registration omitted access token"
user_id=$(jq -er '.user.id' "$tmpdir/register.json") || fail "registration omitted user id"
curl -fsSk "$base_https/api/v1/resumes" \
  -H "Authorization: Bearer $token" \
  -F "file=@$tmpdir/smoke.pdf;type=application/pdf" \
  > "$tmpdir/upload.json" || fail "synthetic résumé upload"
resume_id=$(jq -er '.id' "$tmpdir/upload.json") || fail "upload omitted résumé id"

status=""
for i in $(seq 1 90); do
  curl -fsSk "$base_https/api/v1/resumes/$resume_id" \
    -H "Authorization: Bearer $token" > "$tmpdir/resume.json" || fail "résumé status request"
  status=$(jq -er '.status' "$tmpdir/resume.json") || fail "résumé status missing"
  case "$status" in
    extracted|failed) break ;;
    file_not_found) fail "worker could not find uploaded résumé" ;;
  esac
  sleep 1
done
case "$status" in
  extracted|failed) : ;;
  *) fail "worker did not reach a terminal résumé status (last: $status)" ;;
esac

file_key="resumes/$user_id/$resume_id.pdf"
worker_hash() {
  docker compose -f compose.prod.yml exec -T worker python -c \
    'import asyncio,hashlib,sys; from app.infra.storage.local import LocalFileStore; data=asyncio.run(LocalFileStore("/app/var/files").get(sys.argv[1])); print(len(data),hashlib.sha256(data).hexdigest())' \
    "$file_key"
}
before=$(worker_hash) || fail "worker could not read uploaded résumé"
docker compose -f compose.prod.yml restart api worker >/dev/null || fail "api/worker restart"
ready=false
for i in $(seq 1 60); do
  if curl -fsSk "$base_https/health/ready" >/dev/null 2>&1; then ready=true; break; fi
  sleep 2
done
[ "$ready" = true ] || fail "stack did not recover after api/worker restart"
after=$(worker_hash) || fail "worker could not read résumé after restart"
[ "$before" = "$after" ] || fail "shared résumé contents changed after restart"

echo "SMOKE OK: shared résumé persists across api/worker restart"
