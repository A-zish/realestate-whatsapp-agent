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
# Trial WhatsApp requires a Content Template SID (starts with HX) instead of Body.
TWILIO_WHATSAPP_CONTENT_SID = os.getenv("TWILIO_WHATSAPP_CONTENT_SID", "")

# --- Branding (legacy env; per-account agent_name/city now live on accounts) ---
BUILDER_NAME = os.getenv("BUILDER_NAME", "Your Builder Name")
AGENT_NAME = os.getenv("AGENT_NAME", "Priya")

# Public base URL of THIS server, used to build absolute media URLs and
# the Twilio webhook validation URL. No trailing slash.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

_INSECURE_SESSION_DEFAULT = "dev-insecure-secret-change-me"

# --- Supabase (multi-tenant SaaS: Postgres + Auth + Storage) ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
# Service-role key: used ONLY server-side for Storage uploads (bypasses RLS
# so the bucket needs no manual policy setup). Never expose to a browser.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
# Direct Postgres connection string (from Supabase project settings), used by
# SQLAlchemy for accounts/leads/properties. Distinct from Supabase's REST API.
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Signs the session cookie. Must be set — the insecure default is refused at boot.
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
# Session cookie Secure flag. Defaults on for https PUBLIC_BASE_URL.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower()
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


def cookie_secure() -> bool:
    """HttpOnly cookies also need Secure on HTTPS so they are not sent over HTTP."""
    flag = COOKIE_SECURE
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return PUBLIC_BASE_URL.startswith("https://")


def assert_secure_session_secret() -> None:
    """Refuse to boot with a missing or well-known session signing key."""
    secret = (SESSION_SECRET or "").strip()
    if not secret or secret == _INSECURE_SESSION_DEFAULT:
        raise RuntimeError(
            "SESSION_SECRET is missing or still the insecure default. "
            "Set a random value: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
