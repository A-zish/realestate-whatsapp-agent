# Render: point production at feat/pilot-saas

Live host today: `https://realestate-whatsapp-agent-006r.onrender.com`

As of the last agent check, `/signup` did **not** yet show “A Ramatech product” — the service is still on an older branch (likely `main`).

## Dashboard steps (required)

1. Open [Render Dashboard](https://dashboard.render.com) → service `realestate-whatsapp-agent` (or your renamed service).
2. **Settings → Build & Deploy → Branch** → set to `feat/pilot-saas`.
3. Confirm env vars (see `docs/PILOT_RUNBOOK.md` §4):  
   `DATABASE_URL`, `SESSION_SECRET`, `ENCRYPTION_KEY`, `GROQ_API_KEY`,  
   `PUBLIC_BASE_URL=https://realestate-whatsapp-agent-006r.onrender.com`  
   (adjust host if your service URL differs).
4. **Manual Deploy** → Deploy latest commit.
5. Wait for deploy green; start command runs `alembic upgrade head` (includes `0006` WhatsApp delivery columns).

## Smoke after deploy

```bash
LIVE=https://realestate-whatsapp-agent-006r.onrender.com
curl -sS "$LIVE/health"
curl -sS "$LIVE/signup" | grep -o 'Ramatech\|Start your builder pilot' | sort -u
# Expect: Ramatech and Start your builder pilot
```

Then: signup → onboarding → copy lead link → open `/demo/<slug>` → chat (needs Groq).

## If you prefer main

Merge PR from `feat/pilot-saas` → `main` and keep Render on `main`. Either path is fine; branch and deployed code must match.
