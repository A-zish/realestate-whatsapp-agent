# LeadPilot by Ramatech — Pilot runbook

Self-serve pilot for builders and brokers. **Qualification layer** between
Google Ads / forms and the call centre. Not a CRM. Not WhatsApp-first.

**Product line:** LeadPilot · **Company:** Ramatech  
**Pilot length:** 30 days · **Billing:** none in this phase

---

## 1. Builder self-onboarding (happy path)

1. Open the live app → **Sign up** (agency name, email, password).
2. Onboarding:
   - Agency / agent / city
   - Add **one** live project (price + location)
   - Copy the **lead link** → paste as Google Ads **final URL** / landing CTA
   - Optional: ingest token or CSV later (skip if Ads → link only)
3. Call team: **Leads → Call now (HOT+WARM)** every morning.
4. Do **not** require WhatsApp for the pilot.

Success criteria for Ramatech ops:

- Link is live on Ads for ≥2 weeks
- Callers actually dial the HOT/WARM queue
- Written feedback: “we would pay ₹X/month if …”

---

## 2. How callers use the product

| View | Who | Action |
|---|---|---|
| Call now (HOT+WARM) | Call centre | Dial these first |
| COLD | Manager | Do not call; read `score_reason` |
| Pending | Ops | Unscored CSV/import — not call-ready |
| Lead detail | Caller | Transcript + Call / mark visit |

Delete invalid CSV numbers (Leads → select → Delete, or **Delete all pending**)
before any WhatsApp opener blast. Openers refuse >10 numbers at once.

---

## 3. When WhatsApp is / isn’t ready

| Situation | Do this |
|---|---|
| Pilot / Twilio trial | Use **lead link** only. Trial shows “Twilio Trial” + template ContentSid — not builder branding. |
| Friends must be verified recipients | Console → Messaging → Try out WhatsApp (max 5). |
| Brand name + real opener text | Meta Business Manager + WABA + approved template + Twilio WhatsApp sender. Then paste SID, token, From, **ContentSid (HX…)** on Channels → WhatsApp. |
| Inbound AI replies | Public `PUBLIC_BASE_URL` + Twilio webhook to `/webhook` (localhost will not receive Meta traffic). |

WhatsApp is **Channels → WhatsApp**, not a required onboarding step.

---

## 4. Render deploy checklist (ops)

Hosting is **Render** (FastAPI long-running process). Do not host the app on Vercel.

### Env vars (Dashboard → Environment)

Required:

- `DATABASE_URL` — Supabase session pooler Postgres URI
- `SESSION_SECRET` — random hex 32+
- `ENCRYPTION_KEY` — Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `GROQ_API_KEY`
- `PUBLIC_BASE_URL` — `https://<service>.onrender.com` (no trailing slash)

Recommended:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `STORAGE_BUCKET=property-media`
- `GROQ_MODEL=llama-3.3-70b-versatile`

Optional WhatsApp:

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `TWILIO_WHATSAPP_CONTENT_SID` — trial/template HX… SID

`COOKIE_SECURE` is derived from HTTPS `PUBLIC_BASE_URL` when unset.

### Deploy steps

1. Push branch `feat/pilot-saas` (or merge to the branch Render tracks).
2. Render service uses `render.yaml`: build `pip install -r requirements.txt`,
   start `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Smoke:
   - `GET /health` → `{"status":"ok"}`
   - `/signup` → onboarding → dashboard
   - Open `/demo/<slug>` → chat (needs Groq)
   - Caller queue defaults to HOT+WARM
4. Share URL with 1–2 internal Ramatech testers before external builders.

### Branch / service

- Repo: `A-zish/realestate-whatsapp-agent`
- Prefer deploying **`feat/pilot-saas`** until merged to `main`.
- Current public host (if unchanged): `https://realestate-whatsapp-agent-006r.onrender.com`
- **Ops action:** In Render → service → Settings → Build & Deploy → set Branch to `feat/pilot-saas` → Manual Deploy. Confirm env vars above (especially `PUBLIC_BASE_URL`, `SESSION_SECRET`, `ENCRYPTION_KEY`, `GROQ_API_KEY`, `DATABASE_URL`). After deploy, signup page must show **“A Ramatech product”**.
- Until that branch switch (or merge to `main`), production may still serve the pre-pilot UI.

---

## 5. Subscription (deferred — after pilot feedback)

**Do not implement Razorpay / plans until ≥2 pilots say they would keep paying.**

When ready (Phase 5):

- Account fields: `plan`, `pilot_ends_at`, `billing_status`
- Razorpay checkout + webhook
- Soft limits (conversations / month)

Indicative future pricing (document only, not in product yet):

| Plan | Who | Indicative |
|---|---|---|
| Qualify | 1 project, 1 city | ₹8–15k / month |
| Team | Multi-project | ₹25–40k / month |
| WhatsApp add-on | Real WABA only | +₹10–20k |

Invoice as **Ramatech**; product name **LeadPilot**.

---

## 6. Weekly pilot review script

1. Ads: clicks vs chats started
2. HOT / WARM / COLD mix (if ~80% HOT, scoring is wrong)
3. Are callers skipping COLD?
4. One quote on willingness to pay

If the builder will not put the link on live Ads, the pilot failed — not the model.
