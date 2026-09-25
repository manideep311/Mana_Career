# Mana Career — Production Runtime Hardening Design

- **Date:** 2026-09-25
- **Status:** Proposed for review
- **Parent product:** [Mana Career system design](2026-08-30-mana-career-design.md)
- **Product principle:** Preserve user data and make unavailable or unsafe production behavior visible.

---

## 0. Summary

The production Compose stack currently stores résumé files on API-local disk while a separate worker reads them from its own local disk. The production deployment does not mount storage for either container, so parsing can fail and files can disappear when a container is replaced. The rate limiter also sees the proxy container as the caller because Uvicorn does not trust nginx's forwarded headers. Compose additionally supplies a weak default database password.

This tranche hardens that existing deployment without adding a storage vendor or changing the API contract. It gives API and worker a persistent shared filesystem, lets Uvicorn trust forwarded client data only from nginx, removes the weak production database-password fallback, and rejects the known development JWT secret when the API runs with `ENV=prod`.

This tranche does not implement object storage, external search providers, auth refresh concurrency changes, upload streaming, or UI redesign. Those need separate designs. Fake providers remain a production-readiness issue to address in the external-data tranche; this design does not claim to make all production configuration safe.

## 1. Goals and constraints

### Goals

1. A résumé written by the API is readable by the worker after container restart and image replacement.
2. Uploaded files persist outside individual container writable layers and are included in the documented backup and restore procedure.
3. Requests from the public ingress are rate-limited by the actual client IP, while only nginx can supply trusted forwarded headers.
4. Production startup cannot silently use the checked-in example's weak database password or the known development JWT secret.
5. Existing data is preserved during rollout; mounting a new empty directory over existing files must not hide or discard them.

### Constraints

- Keep the `FileStore` API and current local-file implementation.
- Do not introduce S3 or another external service in this tranche.
- Preserve the existing API routes and user-visible workflow.
- Keep the backend API unpublished on host ports; nginx remains the public ingress.
- Keep local development Compose behavior unless a separate configuration change is required for parity.
- Production deployments are single-host portfolio deployments as scoped in the existing runbook, not multi-node or HA.

## 2. Approaches considered

### A. Shared host bind mount and isolated proxy network — recommended

Bind `./backend/var/files` into both API and worker at the same configured container path. The path is visible for host backup, matching the existing runbook's intent. Before the first bind mount, copy files from any running API container into that host directory. Add a dedicated ingress network with a configurable subnet and a fixed nginx address; configure Uvicorn to trust only that address. Keep API and stateful services connected through a separate internal network.

**Trade-offs:** Minimal new runtime machinery and clear backup visibility. Operators must ensure the host directory is writable by the image's non-root UID and protect résumé files and backups as personal data. A configurable network subnet/IP is necessary to avoid collision with existing host networks.

### B. Named Docker volume and proxy network

Use a named volume shared by API and worker. This avoids host ownership setup for normal writes but requires a deliberate backup/restore mechanism and a one-time migration from any existing container filesystem.

**Trade-offs:** Cleaner container ownership and filesystem isolation; less transparent host backup and more operational steps.

### C. Object storage now

Implement the existing S3 `FileStore` option and configure API/worker credentials and bucket policy.

**Trade-offs:** Suitable for multi-host growth, but adds a new external dependency, credentials, lifecycle and restore behavior, and integration testing. It exceeds the first low-risk production tranche and is unnecessary for the documented single-host deployment.

Approach A is selected because it fixes the current API/worker mismatch while keeping the deployment model and storage interface intact.

## 3. Runtime architecture

### 3.1 Résumé file persistence

- Configure one host directory, `./backend/var/files`, as the storage root for both `api` and `worker` in `compose.prod.yml`.
- Set the same absolute in-container path for both services so the current `FILE_STORE_LOCAL_DIR` configuration resolves identically.
- Create the path in the production image and give it to the non-root application UID. On bind mount, document the host ownership requirement and fail visibly on permission errors; do not run the app as root.
- Keep migration and worker services from receiving the volume unless they need it.
- Update the runbook's backup/restore instructions to operate on the configured host directory, include restrictive file permissions, and state that résumé contents are sensitive personal data.
- For an existing deployment, require a backup before changing Compose. Copy files from the current API container into the host directory before enabling the mount, verify expected file counts and sizes, then restart. The rollout must never mount an empty directory over the only copy of existing files.
- Do not delete old container data as part of the rollout. Removing an old container is only safe after the copied data has been verified and the backup is available.

### 3.2 Trusted client IP forwarding

- Add an ingress network shared by nginx, frontend, and API, with a configurable subnet and a reserved, fixed nginx address.
- Attach the API to a separate data network for PostgreSQL and Redis. Keep database and Redis off the ingress network when Compose allows it without breaking health checks or migration ordering. Worker uses the data network only.
- Configure Uvicorn's `forwarded-allow-ips` to the exact nginx address, not `*` and not the whole Docker subnet.
- Configure nginx to overwrite `X-Forwarded-For` with the socket peer address for this direct-to-nginx deployment, preventing a caller-supplied forwarded chain from changing the address Uvicorn trusts. Continue setting `X-Real-IP` and `X-Forwarded-Proto` from nginx's observed request.
- Do not publish the API port to the host. Requests that bypass nginx must not be able to forge the trusted client address.
- Document the ingress IP and subnet settings and how to choose a non-overlapping private subnet. Configuration should fail clearly if the fixed address is outside the configured subnet or conflicts with another attached address.

After this wiring, Starlette's `request.client.host` should resolve to the public client IP for ingress requests, so the existing Redis rate-limit key remains unchanged.

### 3.3 Production secret preflight

- Remove the `POSTGRES_PASSWORD` fallback from `compose.prod.yml`; Compose must require an explicit value before starting production services.
- Add production-only Settings validation that rejects the known `dev-only-change-me` JWT secret and rejects secrets below an explicitly documented minimum strength/length.
- Keep test and development defaults unchanged.
- Do not log secret values or include them in validation errors.
- Do not broaden this tranche into a provider implementation or fake-data policy change. Add that as a separately reviewed external-data design and clearly retain it as a production-readiness follow-up.

## 4. Failure behavior

- If the shared file path is missing or not writable, uploads and worker parsing fail with existing application error handling and structured logs; they must not silently fall back to container-local storage.
- If proxy network settings are invalid, Compose startup or API health checks fail rather than trusting every source.
- If required production secrets are absent or use the development sentinel, production startup fails before serving requests, without printing secret material.
- If an operator cannot migrate old files, they can keep the old deployment running; the new mount is not applied until backup and copy verification are complete.

## 5. Compatibility and rollout

- No database schema migration is required.
- No API endpoint, request, or response changes are expected.
- Compose will require an explicit production DB password. Proxy-network subnet and nginx IP have documented defaults and can be overridden to avoid collisions.
- The rollout is additive and reversible: stop services, retain the host file directory and database volume, revert Compose/configuration if needed, and restart the prior image. Never run `docker compose down -v` in a production restore or rollback path.
- Update README/runbook example values to avoid presenting fallback credentials as production-ready.

## 6. Verification

### Automated checks

- Settings tests prove the development sentinel remains usable in test/development and is rejected under `ENV=prod`; errors contain no secret value.
- Compose/config tests or static assertions prove API and worker use the same storage root, both mount the same host directory, nginx has the reserved ingress address, Uvicorn trusts only that address, and the API has no host-published port.
- Storage integration test writes a file through one `LocalFileStore` instance and reads/deletes it through another instance rooted at the same shared directory.
- A focused middleware integration test verifies a forwarded public IP is used only when the ASGI client is nginx's trusted address and an untrusted peer cannot choose its rate-limit identity via headers.
- Run the existing frontend, backend, lint, type, security, and image checks available in the environment. A production Docker smoke must upload a test PDF, observe worker processing, restart API/worker containers, and verify the file remains readable.

### Manual rollout checks

- Back up PostgreSQL and résumé files before deployment.
- Verify the pre-mount copy against the old container, including file count and aggregate size.
- Verify host ownership/permissions allow UID 10001 and deny access to unrelated host users where practical.
- After start, upload and parse a test résumé, check rate-limit identity with two client IPs through nginx, restart API and worker, then verify the same résumé and parsed state.
- Restore from backups in a non-production environment before declaring operational readiness.

## 7. Out of scope and tracked risks

- S3-compatible storage and multi-host deployments.
- Refresh-token rotation race and frontend refresh single-flight behavior.
- Actual-byte upload limits before buffering the full request.
- Real search integration and production fake-provider rejection/graceful-unavailable UX.
- Full secure-header/CSP policy, external error reporting, tracing, HA, and automated backup scheduling.
- Authenticated multi-workflow visual QA and representative mobile/tablet/desktop review.
- Full backend and container validation on a host with working Python dependencies and Docker daemon.

These remain in the system audit's follow-up queue; this tranche alone does not satisfy the full project definition of done.
