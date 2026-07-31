# Real Estate WhatsApp Lead Agent

Backend service that imports real-estate leads, opens a WhatsApp conversation
via Twilio, qualifies each lead with an AI agent (Groq), scores them
Hot/Warm/Cold, and writes everything back to a Google Sheet (the dashboard).
Also includes a shareable **web chat demo** (no WhatsApp needed) and an
**admin panel** for managing property inventory with photo/video uploads.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then fill in your values
```

Required env vars (see `.env.example`): `GROQ_API_KEY`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`.

Run locally:
```powershell
uvicorn app.main:app --reload --port 8000
```
- `GET /health` — liveness check
- `GET /demo` — web chat demo (real agent + sheet, no WhatsApp needed)
- `GET /admin/leads`, `GET /admin/properties` — admin panel (HTTP Basic auth via `ADMIN_USER`/`ADMIN_PASSWORD`)
- `POST /webhook` — Twilio WhatsApp webhook

For WhatsApp testing, expose the local server with a tunnel (e.g. `cloudflared tunnel --url http://localhost:8000`)
and set that URL + `/webhook` as the Twilio Sandbox's "When a message comes in".

## Deploying to a permanent URL (Render, free tier)

The web chat demo and admin panel need to be reachable at a stable URL — not
a laptop-dependent dev tunnel — for anything beyond your own testing.
[Render](https://render.com) has a genuinely free web-service tier (no card
required) and this repo includes a `render.yaml` blueprint for it.

**1. Push this repo to GitHub** (skip if you already have a GitHub account and repo set up):
```powershell
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

**2. Create a Render account** at [render.com](https://render.com) (GitHub sign-in is fastest — free, no credit card for the free tier).

**3. New → Blueprint**, connect the GitHub repo you just pushed. Render reads
`render.yaml` and creates the web service automatically.

**4. Fill in the environment variables** Render asks for (values with
`sync: false` in `render.yaml` aren't pre-filled — copy them from your local
`.env`):
- `GROQ_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the **entire JSON key file contents**
  as the value (not a file path — Render can't see local files). The app
  detects JSON-shaped values automatically.
- `ADMIN_USER`, `ADMIN_PASSWORD`

Leave `PUBLIC_BASE_URL` blank for the first deploy.

**5. Deploy.** Render builds and gives you a permanent URL like
`https://realestate-whatsapp-agent.onrender.com`.

**6. Set `PUBLIC_BASE_URL`** to that exact URL in Render's environment
variables (used to build public links for uploaded property photos) — this
triggers an automatic redeploy.

**7. Point Twilio at it**: Twilio Console → WhatsApp Sandbox settings →
"When a message comes in" → `https://<your-render-url>/webhook`.

### Known limitations of the free tier
- **Cold start**: the free plan spins the service down after ~15 minutes of
  no traffic; the next request takes ~30-50s to wake it up. Open the `/demo`
  link yourself a minute before showing it to someone, to warm it up.
- **Ephemeral disk**: property photos uploaded via `/admin/properties` are
  stored on local disk and are **lost when the service restarts** (idle
  spin-down or a redeploy). For anything beyond a same-session demo, prefer
  pasting external image URLs directly into the `properties` sheet tab, or
  re-upload shortly before a meeting. A persistent-storage upgrade (e.g. S3)
  is a natural next step before real production use.

## Project layout

```
app/
  config.py       # env-var config (secrets only via environment)
  sheets.py       # Google Sheet access — leads + properties tabs
  agent.py        # the AI conversation agent (Groq)
  messages.py     # shared canned message templates
  utils.py        # phone normalization, media URL resolution
  pages.py        # HTML for the admin panel + web chat demo
  main.py         # FastAPI app: /webhook, /demo/*, /admin/*
  twilio_client.py
scripts/
  send_test.py, send_openers.py, import_leads.py, ...
data/
  properties.json # demo inventory seed (placeholder data)
  media/          # uploaded property photos (git-ignored, ephemeral on free hosting)
```

## Notes / constraints

- **Twilio WhatsApp sandbox** is the transport for WhatsApp testing. You can
  only freely message a number after it has joined the sandbox. A real
  WhatsApp Business number (Meta verification + approved templates) is a
  separate, later step for messaging arbitrary leads.
- **Secrets via environment variables only.** `.env` and `service_account.json`
  are git-ignored — never commit them.
