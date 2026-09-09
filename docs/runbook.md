# Mana Career — Deployment Runbook

The production stack is `compose.prod.yml`: Postgres 16 + pgvector, Redis 7, the
FastAPI `api`, the ARQ `worker`, the Next.js standalone `frontend`, and an
`nginx` reverse proxy terminating TLS. A one-shot `migrate` service runs
`alembic upgrade head` before `api`/`worker` start.

`AI recommends -> AI prepares -> Human decides` — nothing is emailed without an
explicit in-app approval; see `SECURITY.md` and `docs/threat-model.md`.

## 1. Prerequisites

- Docker Engine 24+ with the Compose v2 plugin, **v2.24 or newer** (`docker compose version`) — the `env_file: required:` key in `compose.prod.yml` needs it.
- A host with ports 80 and 443 free.
- For real TLS: a domain with DNS pointing at the host, and a certificate
  chain + private key. The default below uses a self-signed pair.

## 2. First boot

```bash
git clone https://github.com/manideep311/Mana_Career.git
cd Mana_Career

# 2.1 Configure
cp .env.example .env
#   Edit .env — at minimum (see the PRODUCTION block in the file):
#     ENV=prod
#     JWT_SECRET=$(openssl rand -hex 32)
#     POSTGRES_PASSWORD=<a real secret>
#     REFRESH_COOKIE_SECURE=true
#     LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY=...      (or leave fake)
#     EMBEDDINGS_PROVIDER=voyage + VOYAGE_API_KEY=...        (or leave fake)

# 2.2 TLS material -> deploy/nginx/certs/{fullchain.pem,privkey.pem}
#   Self-signed (dev / demo):
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
#   Real cert: drop your chain + key in as those exact two filenames.

# 2.3 Build images
docker compose -f compose.prod.yml build

# 2.4 Start data services, run migrations, seed reference data
docker compose -f compose.prod.yml up -d db redis
docker compose -f compose.prod.yml run --rm migrate                         # alembic upgrade head
docker compose -f compose.prod.yml run --rm migrate python -m app.seed all  # skills + jobs + learning

# 2.5 Start everything
docker compose -f compose.prod.yml up -d
```

`just` shortcuts: `just prod-up` (build + up), `just seed`, `just smoke-prod`,
`just prod-logs`, `just prod-down`.

## 3. Verify

```bash
docker compose -f compose.prod.yml ps        # every service "healthy" / migrate "exited (0)"
./scripts/smoke-prod.sh                       # -> SMOKE OK
curl -sk https://localhost/health/ready | jq  # {"status":"ready","checks":{...}}
```

Open `https://localhost/` (accept the self-signed warning) — the app shell loads
and talks to the API same-origin through nginx.

## 4. Routine operations

| Task | Command |
|---|---|
| Tail logs | `docker compose -f compose.prod.yml logs -f [service]` |
| Restart one service | `docker compose -f compose.prod.yml restart api` |
| Apply a new migration | `git pull && docker compose -f compose.prod.yml build && docker compose -f compose.prod.yml run --rm migrate && docker compose -f compose.prod.yml up -d` |
| Re-seed reference data | `docker compose -f compose.prod.yml run --rm migrate python -m app.seed all` |
| Stop (keep data) | `docker compose -f compose.prod.yml down` |
| Stop and wipe data | `docker compose -f compose.prod.yml down -v` |

## 5. Backup

Two pieces of state: the `pgdata` volume (all rows) and `backend/var/files`
(uploaded résumés, if `FILE_STORE=local`).

```bash
# Postgres logical dump (run on a schedule, e.g. cron @daily)
docker compose -f compose.prod.yml exec -T db \
  pg_dump -U "${POSTGRES_USER:-mana}" "${POSTGRES_DB:-mana}" | gzip > "backup-$(date +%F).sql.gz"

# Uploaded files
tar czf "files-$(date +%F).tgz" backend/var/files
```

## 6. Restore

```bash
docker compose -f compose.prod.yml up -d db
gunzip -c backup-YYYY-MM-DD.sql.gz | docker compose -f compose.prod.yml exec -T db \
  psql -U "${POSTGRES_USER:-mana}" -d "${POSTGRES_DB:-mana}"
tar xzf files-YYYY-MM-DD.tgz
docker compose -f compose.prod.yml up -d
```

## 7. Upgrade & rollback

**Upgrade:** `git pull` -> `docker compose -f compose.prod.yml build` ->
`docker compose -f compose.prod.yml run --rm migrate` ->
`docker compose -f compose.prod.yml up -d`. Take a backup (section 5) first.

**Rollback:**
- Code/image: check out the previous commit (or set `TAG=` in `.env` to a
  previously built image tag) and `docker compose -f compose.prod.yml up -d`.
- Schema: `docker compose -f compose.prod.yml run --rm migrate alembic downgrade -1`
  (or `alembic downgrade <rev>`). Restore from a dump if a migration was
  destructive.

## 8. TLS in production

Replace `deploy/nginx/certs/{fullchain.pem,privkey.pem}` with your CA-issued
chain and key (same filenames), then `docker compose -f compose.prod.yml
restart nginx`. For automatic renewal, terminate TLS at an upstream load
balancer or add an ACME sidecar — out of scope here (single-tenant portfolio).

## 9. Out of scope (see the Phase 14 spec §3)

Kubernetes/Helm, cloud IaC, managed Postgres/Redis, a CDN, ACME automation,
multi-node/HA, secret managers, log shipping/APM, pushing images to a registry,
the S3 `FileStore` adapter, load/soak testing.
