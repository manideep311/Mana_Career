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
just init-env        # or: bash ./scripts/init-env.sh
#   Writes .env from .env.example with a generated 64-char JWT_SECRET and a
#   random POSTGRES_PASSWORD (it never overwrites an existing .env).
#   compose.prod.yml always runs the backend with ENV=prod, which refuses to
#   start on placeholder secrets, insecure cookies, wildcard CORS, or fake AI
#   providers. Then choose ONE of:
#     Real providers:  LLM_PROVIDER=anthropic   + ANTHROPIC_API_KEY=...
#                      EMBEDDINGS_PROVIDER=voyage + VOYAGE_API_KEY=...
#     Labelled demo:   DEMO_MODE=true   (keeps the fake providers; the UI says so)
#   Optional:          SEARCH_PROVIDER=tavily + SEARCH_API_KEY=...  (web research)
#   Network (defaults are fine): PROXY_SUBNET, NGINX_PROXY_IP, PROXY_DYNAMIC_RANGE

# 2.2 TLS material -> deploy/nginx/certs/{fullchain.pem,privkey.pem}
#   Self-signed (dev / demo):
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -subj "/CN=localhost"
#   Real cert: drop your chain + key in as those exact two filenames.

# 2.3 Prepare shared résumé storage (creates it if absent, sets ownership to
#     container UID/GID 10001, and keeps existing files).
bash ./scripts/prepare-prod.sh

# 2.4 Build images
docker compose -f compose.prod.yml build

# 2.5 Start data services, run migrations, seed reference data
docker compose -f compose.prod.yml up -d db redis
docker compose -f compose.prod.yml run --rm migrate                         # alembic upgrade head
docker compose -f compose.prod.yml run --rm migrate python -m app.seed all  # skills + jobs + learning

# 2.6 Start everything
docker compose -f compose.prod.yml up -d
```

`just` shortcuts: `just prod-up` (prepare storage, build + up), `just seed`, `just smoke-prod`,
`just prod-logs`, `just prod-down`.

Run the storage preparation step before direct `docker compose` startup too. It
is safe to repeat after a fresh boot or completed migration and does not remove
or replace résumé files. On a first upgrade, the guard requires explicit
migration confirmation. On a host without passwordless sudo, run it as root
(for example, `sudo bash ./scripts/prepare-prod.sh`).

## 3. Verify

```bash
docker compose -f compose.prod.yml ps        # every service "healthy" / migrate "exited (0)"
./scripts/smoke-prod.sh                       # -> SMOKE OK
curl -sk https://localhost/health/ready | jq  # {"status":"ready","checks":{...}}
```

The default `smoke-prod.sh` run checks HTTP health and does not write application
data. Set `SMOKE_UPLOAD_PERSISTENCE=1` only on a disposable stack to also create
a synthetic account and résumé, restart API and worker, and verify the file
remains readable. That extended check leaves its account and uploaded test file
in the database and file store; CI removes them with the disposable stack.

Open `https://localhost/` (accept the self-signed warning) — the app shell loads
and talks to the API same-origin through nginx.

Production refuses the fake providers unless `DEMO_MODE=true`, and the UI
labels a demo deployment as such (it reads `GET /api/v1/meta`). Web research
is optional: with `SEARCH_PROVIDER=none` the agent reports the research step as
skipped. With `SEARCH_PROVIDER=tavily`, search results include source URLs,
provider publication dates when available, and the retrieval timestamp; an
unknown publication date is preserved as unknown rather than presented as fresh
evidence. Provider throttling and transient server errors get bounded retries;
a provider outage yields an unavailable research result without substituting
fabricated search hits. Retrieved web text is always fenced as untrusted data
before it reaches a model prompt.

Every HTTPS response carries HSTS, a same-origin Content-Security-Policy,
`X-Frame-Options: DENY`, `nosniff`, a `Referrer-Policy` and a
`Permissions-Policy`; nginx and Next.js don't advertise their versions. The
API's OpenAPI schema and Swagger/ReDoc UIs are not served in production.

Background jobs retry transient failures (5 s, 10 s, 20 s backoff, three
attempts) and then record an explicit failure the UI shows. A sweeper runs
every five minutes and fails anything still "in progress" 20 minutes after its
last status change (for example after a worker crash), so nothing spins
forever. `docker compose ps` shows the worker as unhealthy if its Redis
heartbeat stops; plain Docker does not restart unhealthy containers, so alert on
it or restart the worker by hand.

The API has no published host port. Production Compose separates the `data`
bridge (database, Redis, migration job, worker) from `ingress` (frontend and
nginx); the API joins both. Nginx is assigned `NGINX_PROXY_IP` on
`PROXY_SUBNET`, and Uvicorn trusts forwarded headers only from that exact IP.
Nginx overwrites `X-Forwarded-For` using its direct socket peer. This assumes
nginx receives public traffic directly. If an upstream load balancer is added,
configure its trusted proxy chain explicitly before relying on client IPs.

Defaults are `PROXY_SUBNET=172.30.0.0/24` and `NGINX_PROXY_IP=172.30.0.2`.
Check that the subnet does not overlap the host LAN, VPN, or another Docker
network. If it does, choose a non-overlapping bridge CIDR and an unused address
inside it, then update both environment values together. Do not configure
Uvicorn to trust every peer or the entire bridge subnet.

## 4. Routine operations

| Task | Command |
|---|---|
| Tail logs | `docker compose -f compose.prod.yml logs -f [service]` |
| Restart one service | `docker compose -f compose.prod.yml restart api` |
| Apply a new migration | `git pull && docker compose -f compose.prod.yml build && docker compose -f compose.prod.yml run --rm migrate && docker compose -f compose.prod.yml up -d` |
| Re-seed reference data | `docker compose -f compose.prod.yml run --rm migrate python -m app.seed all` |
| Back up now | `just backup` (see section 5) |
| Check the worker heartbeat | `docker compose -f compose.prod.yml exec worker arq --check app.worker.main.WorkerSettings` |
| Stop (keep data) | `docker compose -f compose.prod.yml down` |
| Stop and wipe data | `docker compose -f compose.prod.yml down -v` |

## 5. Backup

Two pieces of state: the `pgdata` volume (all rows) and `backend/var/files`
(uploaded résumés, if `FILE_STORE=local`). The API and worker share this host
directory at `/app/var/files`; the application runs as UID 10001 in both
containers. Restrict host access because résumé files contain personal data.

`scripts/backup.sh` (`just backup`) writes both into `./backups` (or
`$BACKUP_DIR`) with a UTC timestamp:

- `db-<stamp>.dump` — a `pg_dump --format=custom` dump. The script reads it
  back with `pg_restore --list` and refuses to keep a dump it can't read.
- `files-<stamp>.tgz` — the résumé store, archived through the `api`
  container (the host directory is private to UID 10001).

Files older than `$BACKUP_KEEP_DAYS` (default 14) are removed. CI runs the
script against its disposable stack on every push.

```bash
just backup
# Schedule daily at 03:15 (crontab -e on the host):
15 3 * * *  cd /srv/mana-career && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Copy `./backups` off the host (object storage, another machine). A backup
that only lives next to the database it protects is not a backup.

## 6. Restore

```bash
docker compose -f compose.prod.yml up -d db api
# Database: drop and recreate the objects contained in the dump.
docker compose -f compose.prod.yml exec -T db \
  pg_restore --clean --if-exists -U "${POSTGRES_USER:-mana}" -d "${POSTGRES_DB:-mana}" \
  < backups/db-YYYYMMDDTHHMMSSZ.dump
# Résumé files: unpack through the api container (runs as UID 10001).
docker compose -f compose.prod.yml exec -T api tar -xzf - -C /app/var \
  < backups/files-YYYYMMDDTHHMMSSZ.tgz
docker compose -f compose.prod.yml up -d
```

## 7. Move existing uploads to the shared host directory

Do this once before deploying the Compose file with the bind mount. The old
containers may hold uploads only in the API container's writable layer. Stop
both writers, copy from the API container to a staging directory, and verify
the copy before moving it into the mount source. Do not start the new stack if
the checks differ.

```bash
# Record a source manifest while the API container is still running.
docker compose -f compose.prod.yml exec -T api sh -c \
  'cd /app/var/files && find . -type f -print0 | sort -z | xargs -0 -r sha256sum' > /tmp/files-source.sha256

# Stop writes, copy from the old API container, and compare before switching.
docker compose -f compose.prod.yml stop api worker
mkdir -p backend/var/files.stage
docker compose -f compose.prod.yml cp api:/app/var/files/. backend/var/files.stage/
tar czf "files-pre-mount-$(date +%F).tgz" -C backend/var/files.stage .
(cd backend/var/files.stage && find . -type f -print0 | sort -z | xargs -0 -r sha256sum) > /tmp/files-stage.sha256
test "$(wc -l < /tmp/files-source.sha256)" -eq "$(wc -l < /tmp/files-stage.sha256)"
diff -u /tmp/files-source.sha256 /tmp/files-stage.sha256

mkdir -p backend/var/files
test -z "$(find backend/var/files -mindepth 1 -print -quit)"
cp -a backend/var/files.stage/. backend/var/files/
sudo chown -R 10001:10001 backend/var/files
sudo chmod -R u=rwX,go= backend/var/files
rm -rf backend/var/files.stage
```

Keep the archive in the protected backup location; it contains personal data.
Then run `FILE_STORE_MIGRATION_CONFIRMED=1 bash ./scripts/prepare-prod.sh`
and start the new stack with `docker compose -f compose.prod.yml up -d`. The
confirmation is required while an existing API container does not yet use the
shared host store, even when the copied directory is nonempty. If the old
container was verified to contain no uploads, the same explicit confirmation
applies. For later upgrades, `just prod-up` checks that existing API containers
already use the shared store and does not need the confirmation. Confirm the
API and worker can read the same test upload before resuming normal traffic.

## 8. Upgrade & rollback

**Upgrade:** take a backup (section 5) first. Before the first deployment of
the shared file-store bind mount, complete section 7 while the old API container
is still available. Then run `FILE_STORE_MIGRATION_CONFIRMED=1 just prod-up` to
prepare storage, build images, and start the stack. This one-time confirmation
is needed only for the first mount; later `just prod-up` runs verify that the API
already uses the shared host store. For a manual rollout, use the confirmed
preparation command in section 7 before building and starting Compose.

**Rollback:**
- Code/image: check out the previous commit (or set `TAG=` in `.env` to a
  previously built image tag) and `docker compose -f compose.prod.yml up -d`.
- Schema: `docker compose -f compose.prod.yml run --rm migrate alembic downgrade -1`
  (or `alembic downgrade <rev>`). Restore from a dump if a migration was
  destructive.

## 9. TLS in production

Replace `deploy/nginx/certs/{fullchain.pem,privkey.pem}` with your CA-issued
chain and key (same filenames), then `docker compose -f compose.prod.yml
restart nginx`. For automatic renewal, terminate TLS at an upstream load
balancer or add an ACME sidecar — out of scope here (single-tenant portfolio).

### Temporary public demo through a Cloudflare tunnel

To share a running stack without opening ports:

```bash
cloudflared tunnel --url https://localhost:443 --no-tls-verify
```

It prints a `https://<random>.trycloudflare.com` address that lasts as long as
the command runs. Point it at nginx's port 443 (not the frontend or port 80:
the frontend calls the API same-origin, and port 80 only redirects).

Every visitor then reaches nginx from the tunnel connector's address, so they
would all share one rate-limit bucket. To give each visitor their own, set
`TRUSTED_PROXY_CIDRS` in `.env` to the address the connector reaches nginx
from — for `cloudflared` on the host that is the ingress network's gateway
(`172.30.0.1/32` with the default `PROXY_SUBNET`) — and restart `api`. The API
then trusts `CF-Connecting-IP` from that address only. Do this only while all
traffic arrives through the tunnel: a client that can reach nginx directly from
that address could set the header itself.

Before sharing any link, confirm `.env` came from `just init-env` (a random
`JWT_SECRET`); the stack refuses to start on the public placeholder anyway.

## 10. Out of scope (see the Phase 14 spec §3)

Kubernetes/Helm, cloud IaC, managed Postgres/Redis, a CDN, ACME automation,
multi-node/HA, secret managers, log shipping/APM, pushing images to a registry,
the S3 `FileStore` adapter, load/soak testing.
