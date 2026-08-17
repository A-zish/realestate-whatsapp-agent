# LeadPilot by Ramatech — AI lead qualification for real estate

**A Ramatech product.** Multi-tenant pilot SaaS for builders and brokers.
Each agency signs up, gets an AI qualifier, a shareable **lead link** (Google Ads
CTA), and a caller queue of **HOT / WARM** leads — so the call centre stops
dialling junk Ads clicks. This is a **qualification layer**, not a CRM.

Pilot phase: **30 days, no subscription billing**. Feedback first; Razorpay
plans come after real builders would pay.

Primary channel for pilots: **web lead link**. WhatsApp is optional and needs
Meta Business verification (not Twilio trial “Twilio Trial” branding).

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
| WhatsApp | Twilio (optional; production needs Meta verification + ContentSid) |
| Hosting | **Render** (not Vercel — this is a long-lived Python app) |

---

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
cp .env.example .env               # then fill it in — see below
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Or with Docker Desktop:

```bash
docker compose up --build
```

Open http://localhost:8000/signup and create an agency account.

### Env vars

`.env` is git-ignored. See `.env.example` and [docs/PILOT_RUNBOOK.md](docs/PILOT_RUNBOOK.md).

| Var | What it is |
|---|---|
| `DATABASE_URL` | Postgres connection string (Supabase session pooler preferred) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Storage uploads only |
| `SESSION_SECRET` | Required. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `COOKIE_SECURE` | `false` on localhost; HTTPS on Render implies secure cookies |
| `PUBLIC_BASE_URL` | Public HTTPS URL (Render), no trailing slash |
| `GROQ_API_KEY` | LLM |
| `ENCRYPTION_KEY` | Fernet key for Twilio tokens at rest |
| `TWILIO_*` / `TWILIO_WHATSAPP_CONTENT_SID` | Optional WhatsApp |

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
  templates/     Jinja2 pages (base.html is the shell)
  static/        design system CSS + a little JS
alembic/         schema migrations
docs/            pilot runbook
scripts/         seed + test scripts
```

### The one rule: tenant isolation

Every lead/property query is scoped by `account_id`. Never fall back to
“the only WhatsApp-connected tenant” for inbound webhooks.

---

## Deploy (Render)

See [docs/PILOT_RUNBOOK.md](docs/PILOT_RUNBOOK.md). Service definition: `render.yaml`.
Start command runs `alembic upgrade head` then uvicorn.

Related ops docs:

- [docs/PILOT_GTM_LEAD_LINK.md](docs/PILOT_GTM_LEAD_LINK.md)
- [docs/WHATSAPP_PRODUCTION_WABA.md](docs/WHATSAPP_PRODUCTION_WABA.md)
- [docs/SUBSCRIPTION_DEFERRED.md](docs/SUBSCRIPTION_DEFERRED.md)
