#!/usr/bin/env bash
# Prepare the bind-mounted file store for containers running as UID/GID 10001.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
file_dir="$repo_root/backend/var/files"
compose_file="$repo_root/compose.prod.yml"

# Do not mount an unverified host directory over files in an existing API
# container. A verified migration requires explicit one-time confirmation.
if ! command -v docker >/dev/null 2>&1; then
  echo "Cannot verify existing API containers; install Docker Compose before preparing storage." >&2
  exit 1
fi
if ! existing_apis=$(docker compose -f "$compose_file" ps --all -q api); then
  echo "Could not inspect existing API containers; refusing to prepare storage." >&2
  exit 1
fi

if [ -n "$existing_apis" ]; then
  all_apis_use_store=true
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    if ! mounted_source=$(docker inspect --format \
      '{{range .Mounts}}{{if eq .Destination "/app/var/files"}}{{.Source}}{{end}}{{end}}' \
      "$container_id"); then
      echo "Could not inspect API container $container_id; refusing to prepare storage." >&2
      exit 1
    fi
    if [ "$mounted_source" != "$file_dir" ]; then
      all_apis_use_store=false
    fi
  done <<< "$existing_apis"

  if [ "$all_apis_use_store" != true ] && [ "${FILE_STORE_MIGRATION_CONFIRMED:-0}" != "1" ]; then
    echo "An existing API container does not use the shared host resume store." >&2
    echo "Complete and verify runbook section 7, then rerun with FILE_STORE_MIGRATION_CONFIRMED=1." >&2
    exit 1
  fi
fi

if [ "$(id -u)" -eq 0 ]; then
  install -d -o 10001 -g 10001 -m 0700 "$file_dir"
elif command -v sudo >/dev/null 2>&1; then
  sudo install -d -o 10001 -g 10001 -m 0700 "$file_dir"
else
  echo "Run as root or install sudo to prepare $file_dir for UID/GID 10001." >&2
  exit 1
fi

if [ "$(stat -c '%u:%g:%a' "$file_dir")" != "10001:10001:700" ]; then
  echo "Could not set $file_dir ownership to 10001:10001 and mode 0700." >&2
  exit 1
fi

echo "Prepared $file_dir for the production API and worker (UID/GID 10001)."
