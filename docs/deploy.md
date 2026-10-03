# Deploying for free: Supabase + Render + Vercel + Brevo

```
browser ──► Vercel (website)  ──/api──►  Render (API + background worker)
                                             │            │
                                             ▼            ▼
                                Supabase Postgres    Render Key Value (Redis)
                                Supabase Storage (résumé PDFs)
                                             │
                                             ▼
                                   Brevo (account & application emails)
```

Every service here has a free plan; no card is needed for this setup.

- **Vercel** serves the website and forwards every `/api` request to Render
  (`frontend/middleware.ts`), so the browser only ever talks to one address and
  the sign-in cookie stays first-party.
- **Render** runs the API with the background worker inside the same process
  (`RUN_WORKER_IN_API=true`): the free plan has no worker type and 512 MB of
  memory. Each start applies database migrations and, the first time, loads the
  career catalogue (`SEED_ON_START=true`).
- **Supabase** holds the database (with `pgvector`) and a private bucket for
  uploaded résumés (Render's free plan has no disk).
- **Brevo** sends sign-up confirmations, password resets and application
  emails.

## What "free" means

**The app runs as a labelled demo** (`DEMO_MODE=true`, no AI keys). Once
signed in, a banner at the top of the app says so.

| Works fully | Works differently |
|---|---|
| Accounts, email confirmation, password reset, account export/delete | Résumé details aren't read automatically: after uploading, people type their skills on the review screen and add experience on the Profile page |
| Résumé upload and "How your résumé reads" | Cover letters and tailored résumés use simple templates |
| Career paths, job matching, skill plans (all rule-based, no AI) | Roadmap planning has no AI-written steps |
| Applications: prepare, approve, send, track | |

**The free plans also have limits:**

| Service | Limit | Effect |
|---|---|---|
| Render | Sleeps after 15 min without visitors; ~1 min to wake | The first visit after a quiet spell is slow |
| Render | Mail ports 25/465/587 blocked | Email uses Brevo's port 2525 |
| Render Key Value | Not saved to disk | Queued jobs are lost on a restart; the sweeper fails anything left mid-way |
| Supabase | Pauses after 7 days with no activity | Restore it from the dashboard, or keep it awake (end of this page) |
| Brevo | 300 emails a day | Plenty for a portfolio demo |

**Never paste passwords or keys into chat, commits or screenshots.** Each one
goes straight into the dashboard that needs it.

---

## Step 0: the code must be on GitHub

Render and Vercel deploy from GitHub. The work has to be committed, pushed,
pass CI, and be merged to `main` first.

## Step 1: Supabase (database + file storage)

1. Sign up at supabase.com → **New project**. Choose a strong database
   password (save it in a password manager). Pick the region nearest your
   visitors, e.g. **Mumbai** or **Singapore** for India.
2. **Connection string**: click **Connect** → **Session pooler** and copy the
   URI. Rewrite it into the app's format:

   ```text
   postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?ssl=require
   ```

   - `postgresql://` becomes `postgresql+asyncpg://`
   - add `?ssl=require` at the end
   - put your real password in, URL-encoding special characters (`@` → `%40`,
     `#` → `%23`, `/` → `%2F`)

   Don't use the *Transaction pooler* (port 6543).
3. **Bucket**: **Storage** → **New bucket** → name `resumes`, leave
   **Public** off.
4. **Keys**: **Project Settings** → **API Keys**. Note the **Project URL**
   (`https://<ref>.supabase.co`) and the **secret** key (or the legacy
   `service_role` key). This key can read every stored file.
5. **Switch off Supabase's automatic table API.** This app never uses it, and
   left on, anyone with the project's public key could read user data:
   **Project Settings** → **Data API** → turn it **off** (or remove `public`
   from the exposed schemas). There's one more lock-down step after the first
   deploy (step 6).

## Step 2: Brevo (email)

1. Sign up at brevo.com (free plan).
2. **Senders, domains & dedicated IPs** → **Senders** → add the address emails
   should come from (your Gmail is fine) and click the verification link Brevo
   sends you.
3. **SMTP & API** → **SMTP** tab: note the **Login** and create an **SMTP
   key**. The key is your SMTP password.

(Got your own domain? Resend also works: `SMTP_HOST=smtp.resend.com`,
`SMTP_PORT=2587`, `SMTP_USERNAME=resend`, password = a Resend API key.)

## Step 3: Render (the API)

1. Sign up at render.com with GitHub. **New** → **Blueprint** → choose this
   repository (branch `main`). Render reads `render.yaml`.
   - Not in Asia? Change both `region: singapore` lines in `render.yaml` to the
     region nearest your Supabase project first (`frankfurt`, `oregon`, `ohio`,
     `virginia`).
2. Render asks for the values marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the connection string from step 1.2 |
   | `APP_BASE_URL` | the Vercel address you'll use, e.g. `https://mana-career.vercel.app` |
   | `CORS_ORIGINS` | the same Vercel address |
   | `SUPABASE_URL` | the Project URL from step 1.4 |
   | `SUPABASE_SERVICE_ROLE_KEY` | the secret key from step 1.4 |
   | `SMTP_USERNAME` | Brevo SMTP login (step 2.3) |
   | `SMTP_PASSWORD` | Brevo SMTP key (step 2.3) |
   | `EMAIL_FROM_ADDRESS` | the sender you verified in Brevo (step 2.2) |

3. **Apply**. The first build takes a few minutes. When it's live, open
   `https://<your-service>.onrender.com/health`: it should show
   `{"status":"ok"}`. The career catalogue loads during this first start.
4. Open the service → **Environment** and copy `PROXY_SHARED_SECRET` (Render
   generated it) for the next step.

From now on Render redeploys automatically after each push to `main` whose CI
passes.

## Step 4: Vercel (the website)

1. Sign up at vercel.com with GitHub. **Add New** → **Project** → import this
   repository → set **Root Directory** to `frontend`. Vercel detects Next.js.
2. **Environment Variables**:

   | Variable | Value |
   |---|---|
   | `API_ORIGIN` | `https://<your-service>.onrender.com` |
   | `PROXY_SHARED_SECRET` | the value copied from Render |
   | `NEXT_PUBLIC_API_BASE_URL` | `/` |
   | `NEXT_PUBLIC_SITE_URL` | `https://<your-project>.vercel.app` |
   | `ENABLE_EXPERIMENTAL_COREPACK` | `1` (builds with the pnpm version the repo pins) |

3. **Deploy**. If the address Vercel gives you differs from what you typed
   into Render, update `APP_BASE_URL` and `CORS_ORIGINS` in Render (saving
   restarts it).

## Step 5: try it

1. Open the Vercel address. The first load can take about a minute while
   Render wakes up.
2. **Create an account.** The confirmation email should arrive (check spam
   the first time); its link opens the Vercel site.
3. **Upload a résumé.** Type your skills on the review screen and confirm; add
   experience on the Profile page. Then look at the dashboard, career paths
   and jobs.
4. **Prepare an application and approve it.** The email arrives in your own
   inbox (`EMAIL_DELIVERY=redirect` never emails an employer).

## Step 6: lock the database down

Now that every table exists, in Supabase open **SQL Editor** and run this.
It switches on row-level security with no access rules, so Supabase's own API
roles can see nothing. The app is unaffected because it connects as the
tables' owner. Run it again after any update that adds tables.

```sql
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;
```

## Optional: keep it awake

A free uptime monitor (e.g. UptimeRobot) checking
`https://<your-service>.onrender.com/health/ready` every 10 minutes stops Render
sleeping. That uses about 744 of Render's 750 free hours a month, and because
that address touches the database, it also stops Supabase pausing.

## Turning on real AI later

In Render → **Environment**, change these and save (the service restarts):

- **Writing and résumé reading**: `LLM_PROVIDER=anthropic`,
  `ANTHROPIC_API_KEY=<key>` (pay-as-you-go; set a monthly limit in Anthropic's
  console).
- **Semantic search**: `EMBEDDINGS_PROVIDER=voyage`, `EMBED_MODEL=voyage-3`,
  `VOYAGE_API_KEY=<key>`. Then reload the catalogue so its vectors match: from
  your computer in `backend/`, with `DATABASE_URL`, `EMBEDDINGS_PROVIDER`,
  `EMBED_MODEL` and `VOYAGE_API_KEY` set the same way, run
  `uv run python -m app.seed all`.
- With both real providers on, set `DEMO_MODE=false`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Render deploy fails at start with a settings error | A required variable is empty; the message names it (secret values are never printed). |
| `password authentication failed` or `prepared statement` errors | Use the *Session pooler* string on port 5432, with the password URL-encoded. |
| Signed out on every page reload | The site is calling Render directly: `NEXT_PUBLIC_API_BASE_URL` must be `/` and `API_ORIGIN` set; redeploy Vercel after changing them. |
| Visitors hit "too many requests" (429) errors far too easily | `PROXY_SHARED_SECRET` differs between Vercel and Render, so everyone shares Vercel's addresses. |
| No emails | Check Brevo's logs; the sender must be verified, and the port must be 2525 on Render's free plan. |
| Out of memory on Render | Lower `WORKER_MAX_JOBS` (e.g. to 2). |
