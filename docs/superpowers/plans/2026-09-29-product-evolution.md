# Product Evolution — audit fixes + career-guidance redesign

Branch: `product-evolution` (off local `main@82bfad9`, which carried 7 unpushed hardening commits).
Source of requirements: the 2026-09-29 audit (in chat) + the 51-point product brief.

## Rulings (decisions the brief delegated)

- **R1 Tavily → Option B (optional).** `SEARCH_PROVIDER=none|fake|tavily`, default `none`. Production no
  longer requires a paid key. `none` makes `job_research` report "Web research isn't configured" instead of
  failing. Web content stays fenced (`<untrusted_data>`), defanged and clamped. Integrating research into
  generation is left as future work because nothing consumes `research_notes` yet.
- **R2 API docs** are served only outside production (`docs_url`/`redoc_url`/`openapi_url` = `None` when
  `ENV=prod`). The prod smoke uses `/api/v1/health` instead of `/api/openapi.json`.
- **R3 JWT secret.** `dev-only-*` and well-known placeholders are rejected in every environment; production
  also requires ≥32 chars. `.env.example` ships no secret; `scripts/init-env.sh` / `just init-env` generate
  one. `compose.prod.yml` forces `ENV=prod` and requires `JWT_SECRET`.
- **R4 Demo mode.** Production rejects `fake` providers unless `DEMO_MODE=true` is set explicitly; the
  public `/api/v1/meta` endpoint exposes `demo_mode` so the UI can say so honestly. The deterministic
  guidance baselines (below) keep demo mode useful without API keys.
- **R5 Sessions.** Access tokens gain `iss`, `aud` and `sid` (the refresh family id); `get_current_user`
  rejects a token whose family has no live refresh token (logout / reuse / password change revoke the
  session immediately). `rotate()` locks the row (`FOR UPDATE`) and allows a 15 s grace window for a
  parallel refresh with the just-rotated token (multi-tab), instead of treating it as theft.
- **R6 CSP** is set at nginx. Next.js App Router emits inline RSC bootstrap scripts, so `script-src` keeps
  `'unsafe-inline'` (no nonce infra); everything else is locked to `'self'`, `frame-ancestors 'none'`,
  `object-src 'none'`.
- **R7 Deterministic-first guidance.** Résumé analysis, skill evidence, career paths, skill-gap
  prioritisation and a roadmap milestone fallback are deterministic and grounded in stored data. The LLM
  improves phrasing and extraction when configured; it is never the only path.
- **R8 Rate limiting.** Atomic Lua `INCR` + TTL self-heal; `/ai` GETs use the read bucket;
  `CF-Connecting-IP` is trusted only when the peer is inside `TRUSTED_PROXY_CIDRS`.
- **R9 Uploads.** An ASGI body-size guard caps every request body (route-specific cap for uploads) while
  streaming, so the limit holds without `Content-Length` and without nginx.
- **R10 Workers.** Non-final attempts raise `arq.worker.Retry` with exponential backoff; the final attempt
  marks the resource failed, publishes the failure and writes a dead-letter record. An ARQ cron sweeper
  fails anything left in an in-progress state past its deadline (e.g. after a worker crash).
- **R11 Polling** is bounded (backoff, max duration, stop on terminal state, cleanup on unmount).
- **R12 Branch protection** is a GitHub repository setting → documented for the owner, not applied here.
- **R13 Typography.** A display serif via `next/font` (self-hosted at build; no runtime third-party
  request).
- **R14 Motion.** CSS keyframes + inline SVG only; no animation library; `prefers-reduced-motion` honoured.

## Workstreams

- [x] A. Config & JWT hardening (R3, R4, provider validation, R1, R2)
- [ ] B. Worker retry/backoff/final-failure + stuck-job sweeper (R10) + real-ARQ tests
- [ ] C. Sessions: refresh race (FOR UPDATE + grace), `sid`/`iss`/`aud`, revocation (R5)
- [ ] D. Rate limiter (R8) + client-IP helper
- [ ] E. Upload body guard (R9)
- [ ] F. Ops: compose limits/logging/healthchecks/backups; nginx headers (R6); CI hardening
- [ ] G. Frontend reliability: single-flight refresh, bounded polling, error/not-found/loading pages
- [ ] H. Guidance engine: résumé analysis, skill evidence, career paths, skill-gap detail, roadmap phases
- [ ] I. UI: tokens/typography, landing, paper rocket, contextual progress, dashboard, paths, résumé,
      matching, roadmap, empty states, micro-interactions, responsive, a11y
- [ ] J. Verification + final report

## Ledger

- 2ddb3d1 — finished the 2026-09-25 hardening tranche (Tavily date test fixed, prepare-prod.sh re-encoded
  to ASCII). Branch pushed for CI.
- CI run 36525011401 on 2ddb3d1 caught 3 bugs in the (never-CI'd) tranche, fixed in workstream A:
  nginx fixed IP collided with dynamically assigned api/frontend addresses (added `ip_range`);
  `create_host_path` is dropped from resolved `config` output on the runner's Compose (test now reads
  the source YAML); `prod_settings` fixture built an incomplete prod config.
- Workstream A: placeholder JWT secrets rejected in every env; prod requires >=32-char secret,
  secure cookie, explicit CORS, real providers or DEMO_MODE; providers narrowed to shipped adapters;
  SEARCH_PROVIDER=none default; /api/v1/meta; API schema/docs off in prod; compose forces ENV=prod and
  requires JWT_SECRET; init-env script; LocalFileStore resolved-path guard.
