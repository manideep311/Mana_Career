#!/usr/bin/env bash
# Create .env and backend/.env from their templates with freshly generated
# secrets. Existing files are left alone unless FORCE=1.
#
# Note: Postgres only reads POSTGRES_PASSWORD when its data volume is first
# created. Regenerating it for an existing production volume will lock the app
# out; change the password inside Postgres first (see docs/runbook.md).
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)

gen_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    python3 -c "import secrets, sys; print(secrets.token_hex(int(sys.argv[1])))" "$1"
  fi
}

set_value() {
  # Values are hex, so they are safe inside a sed replacement.
  sed -i.bak "s/^$2=.*/$2=$3/" "$1" && rm -f "$1.bak"
}

write_env() {
  local template=$1 target=$2
  if [ -e "$target" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "$target already exists; leaving it unchanged (FORCE=1 overwrites)."
    return
  fi
  cp "$template" "$target"
  set_value "$target" JWT_SECRET "$(gen_hex 32)"
  if grep -q '^POSTGRES_PASSWORD=' "$target"; then
    set_value "$target" POSTGRES_PASSWORD "$(gen_hex 16)"
  fi
  chmod 600 "$target" 2>/dev/null || true
  echo "Wrote $target with generated secrets."
}

write_env "$repo_root/.env.example" "$repo_root/.env"
write_env "$repo_root/backend/.env.example" "$repo_root/backend/.env"
