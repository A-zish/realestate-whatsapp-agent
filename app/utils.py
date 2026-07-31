"""Small shared helpers."""
import hashlib
import re
from datetime import datetime, timezone

from app import config


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (for the updated_at column)."""
    return datetime.now(timezone.utc).isoformat()


def resolve_media_url(url: str | None) -> str | None:
    """Turn a stored image_url into a fully public URL Twilio can fetch.

    External links (http/https) are returned as-is. A relative path such as
    'media/abc.png' (an uploaded photo) is prefixed with PUBLIC_BASE_URL.
    """
    if not url:
        return None
    url = str(url).strip()
    if url.startswith(("http://", "https://")):
        return url
    if not config.PUBLIC_BASE_URL:
        return url  # nothing to prefix with; best effort
    return f"{config.PUBLIC_BASE_URL}/{url.lstrip('/')}"


def web_session_phone(session_id: str) -> str:
    """Deterministic synthetic 'phone' key for a web-demo chat session.

    Not dialable — the local number always starts with six zeros, which no
    real Indian mobile number can do, so these rows are unmistakably web-demo
    leads (not real WhatsApp contacts) wherever the sheet is viewed.
    """
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    tail = "".join(ch for ch in digest if ch.isdigit())[:4].zfill(4)
    return f"+91000000{tail}"


def normalize_phone(raw: str, default_cc: str = "91") -> str:
    """Normalize a phone number to E.164, e.g. '+919812345678'.

    Handles common messy inputs: 'whatsapp:' prefixes, spaces, dashes,
    parentheses, leading zeros, and bare 10-digit Indian numbers.
    Assumes India (+91) when no country code is present.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    # Drop the WhatsApp channel prefix Twilio uses.
    if s.lower().startswith("whatsapp:"):
        s = s[len("whatsapp:"):]
    # Keep a leading +, strip everything else that isn't a digit.
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)

    if has_plus:
        return "+" + digits

    # No '+'. Decide how to add the country code.
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    if len(digits) == 10:  # bare local Indian mobile number
        return "+" + default_cc + digits
    if digits.startswith(default_cc):
        return "+" + digits
    return "+" + digits
