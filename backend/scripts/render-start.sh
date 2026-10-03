#!/bin/sh
# Render start command: bring the database schema up to date (and, with
# SEED_ON_START=true, load the career catalogue if it's empty), then serve the
# API. With RUN_WORKER_IN_API=true (the free plan) the background worker runs
# inside this same process. Render sets PORT.
set -eu
alembic upgrade head
# Hosts without a shell (Render free) load the career catalogue here, once.
if [ "${SEED_ON_START:-false}" = "true" ]; then
  python -m app.seed if-empty
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
