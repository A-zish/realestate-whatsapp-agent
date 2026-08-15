"""Central config. Secrets come from environment variables only (never hardcode)."""
import os

from dotenv import load_dotenv

# Load .env from the project root if present.
load_dotenv()

# --- LLM provider: Groq (free) ---
# The agent's LLM call lives in app/agent.py and is provider-swappable.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# --- Anthropic (kept for an easy future swap to Claude) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# --- Google Sheets ---
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", "./service_account.json"
)

# --- Branding ---
BUILDER_NAME = os.getenv("BUILDER_NAME", "Your Builder Name")
# The human persona the AI plays (a named sales exec, not a faceless "assistant").
AGENT_NAME = os.getenv("AGENT_NAME", "Priya")

# --- Admin panel (manage inventory) ---
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# Public base URL of THIS server (the tunnel/host), used to build absolute
# image URLs for uploaded property photos so Twilio can fetch them.
# e.g. https://xxxx.trycloudflare.com  (no trailing slash)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# --- Supabase (multi-tenant SaaS: Postgres + Auth + Storage) ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
# Service-role key: used ONLY server-side for Storage uploads (bypasses RLS
# so the bucket needs no manual policy setup). Never expose to a browser.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
# Direct Postgres connection string (from Supabase project settings), used by
# SQLAlchemy for accounts/leads/properties. Distinct from Supabase's REST API.
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Signs our own session cookie (itsdangerous) after Supabase verifies login.
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "property-media")

# Fernet key encrypting third-party credentials (agency Twilio tokens) at rest.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")


def require(*names: str) -> None:
    """Raise a clear error if any required env var is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in."
        )
