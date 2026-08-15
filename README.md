# LeadPilot — AI lead qualification for real estate

Multi-tenant SaaS. Each real estate agency signs up, gets their own AI sales
agent, their own shareable lead-capture link, and a dashboard where every
lead arrives already qualified and scored HOT / WARM / COLD.

The agent qualifies leads over chat (web today, WhatsApp where connected):
captures location, property type, budget and timeline, shows matching
properties from that agency's own inventory, handles objections, and pushes
toward booking a site visit.

---

## Stack

| Layer | Choice |
|---|---|
| Web | FastAPI + Jinja2 templates (server-rendered) |
| UI | Hand-rolled CSS design system (`app/static/css/app.css`) — no build step |
| DB | Postgres (Supabase), SQLAlchemy + Alembic migrations |
| Auth | Self-hosted, PBKDF2-HMAC-SHA256 (stdlib) + signed session cookie |
| File storage | Supabase Storage (property photos/videos) |
| LLM | Groq (`llama-3.3-70b-versatile`) — isolated in `app/agent.py`, swappable |
| WhatsApp | Twilio (sandbox today; production needs Meta verification) |
| Hosting | Render |

---

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt
cp .env.example .env             # then fill it in — see below
alembic upgrade head             # create the schema
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/signup and create an agency account.

### Env vars

`.env` is git-ignored and never committed. Ask the project owner for values,
or point at your own Supabase project for local dev.

| Var | What it is |
|---|---|
| `DATABASE_URL` | Postgres connection string. Use Supabase's **Session pooler** URI (the direct one is IPv6-only and fails on some hosts). Percent-encode special characters in the password. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Used only for Storage uploads |
| `SESSION_SECRET` | Signs session cookies. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GROQ_API_KEY` | The LLM. Free tier at console.groq.com |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` | WhatsApp channel |
| `PUBLIC_BASE_URL` | This server's public URL, used to build shareable/lead links |
| `STORAGE_BUCKET` | Defaults to `property-media` |

---

## How it's organised

```
app/
  main.py        FastAPI routes: auth, dashboard, playground, /demo/<slug>, /webhook
  models.py      SQLAlchemy models: accounts, users, leads, properties
  db.py          ALL data access — every function is account-scoped
  auth.py        password hashing + session cookies
  agent.py       the LLM call, system prompt, JSON parsing
  storage.py     Supabase Storage uploads
  utils.py       phone normalization, media URL resolution
  templates/     Jinja2 pages (base.html is the shell)
  static/        design system CSS + a little JS
alembic/         schema migrations
scripts/         seed + test scripts (run as `python -m scripts.<name>`)
```

### The one rule: tenant isolation

Every lead and property belongs to an `account_id`. **Every function in
`app/db.py` takes `account_id` as its first argument** and only ever touches
that account's rows. There is deliberately no "get all leads across
accounts" function. If you add a query, keep this invariant — it's the whole
security model of the product.

### Playground vs. lead link

Two different things that used to be one confusing URL:

- **`/dashboard/playground`** — the agency testing their own agent. Chat
  history lives in the browser only; **nothing is written to the database.**
- **`/demo/<account-slug>`** — the real, public capture link. Every
  conversation creates and updates a scored lead.

---

## Testing

Scripts under `scripts/` run against a live database, so point `.env` at a
scratch Supabase project before running them.

```bash
python -m scripts._test_ui                  # every page renders
python -m scripts._test_multitenant_e2e     # signup, login, tenant isolation, webhook
python -m scripts._test_storage_upload      # property media upload
python -m scripts.test_agent                # offline agent conversation
```

They clean up the rows they create.

---

## Deploying

Render builds from `render.yaml` and runs
`alembic upgrade head && uvicorn app.main:app`, so migrations apply on every
deploy. Push to `main` → auto-deploy.

Secrets marked `sync: false` in `render.yaml` are set by hand in Render's
**Environment** tab; they are never in the repo.

**Free-tier gotcha:** the service sleeps after ~15 min idle, so the first
request takes ~50s. Open the link a minute before a client demo.

---

## Known gaps / roadmap

- **Team members & roles** — one login per agency today; invites + Owner /
  Manager / Agent roles not built yet
- **Lead import UI** — `scripts/import_leads.py` exists but isn't exposed in
  the dashboard, and still needs account scoping
- **Conversation view** — leads table doesn't yet open the full transcript
- **Human takeover** — no way to pause the AI and reply manually
- **WhatsApp per agency** — one shared Twilio sandbox number; production
  needs Meta business verification + approved templates per agency
- **Billing** — not started
- `app/sheets.py` is dead code from the pre-Postgres version, kept only for
  reference; safe to delete
