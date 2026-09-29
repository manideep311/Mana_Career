#!/usr/bin/env bash
# Back up the production database and uploaded résumé files.
#
#   ./scripts/backup.sh                    # writes into ./backups
#   BACKUP_DIR=/srv/backups BACKUP_KEEP_DAYS=30 ./scripts/backup.sh
#
# Schedule it (see docs/runbook.md), e.g. daily at 03:15:
#   15 3 * * *  cd /srv/mana-career && ./scripts/backup.sh >> backups/backup.log 2>&1
#
# The database dump is verified by listing its contents with pg_restore before
# it is kept. Résumé files are archived through the api container because the
# host directory is private to the container user (UID 10001).
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

compose=(docker compose -f compose.prod.yml)
dest=${BACKUP_DIR:-"$repo_root/backups"}
keep_days=${BACKUP_KEEP_DAYS:-14}
stamp=$(date -u +%Y%m%dT%H%M%SZ)

env_value() {
  # Read KEY from .env without sourcing it; fall back to the compose default.
  local value=""
  if [ -f .env ]; then
    value=$(grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- || true)
  fi
  printf '%s' "${value:-$2}"
}
db_user=$(env_value POSTGRES_USER mana)
db_name=$(env_value POSTGRES_DB mana)

mkdir -p "$dest"
chmod 700 "$dest"

db_file="$dest/db-$stamp.dump"
"${compose[@]}" exec -T db pg_dump -U "$db_user" -d "$db_name" --format=custom > "$db_file.partial"
if ! "${compose[@]}" exec -T db pg_restore --list < "$db_file.partial" > /dev/null; then
  rm -f "$db_file.partial"
  echo "Backup FAILED: the database dump could not be read back." >&2
  exit 1
fi
mv "$db_file.partial" "$db_file"

files_file="$dest/files-$stamp.tgz"
"${compose[@]}" exec -T api tar -czf - -C /app/var files > "$files_file.partial"
tar -tzf "$files_file.partial" > /dev/null
mv "$files_file.partial" "$files_file"

find "$dest" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'files-*.tgz' \) \
  -mtime +"$keep_days" -delete

echo "Backup OK: $(basename "$db_file"), $(basename "$files_file") (kept ${keep_days} days)"
