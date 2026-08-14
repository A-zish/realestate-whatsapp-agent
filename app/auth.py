"""Auth: Supabase verifies credentials, we own the ongoing session.

Split responsibility on purpose:
  - Supabase Auth handles signup/login verification, password hashing, and
    (later) password-reset emails — we never store or check a password.
  - Once verified, THIS app mints its own signed cookie (itsdangerous) that
    just holds {user_id, account_id}. Ongoing requests only need to verify
    that cookie, not talk to Supabase or juggle JWT refresh tokens.

FastAPI usage:
    @app.get("/dashboard")
    def dashboard(account: dict = Depends(get_current_account)): ...

Unauthenticated access raises NotAuthenticated, which app/main.py turns into
a redirect to /login via a registered exception handler.
"""
import logging

import httpx
from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from supabase import Client, create_client

from app import config, db

log = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
_SALT = "realestate-saas-session"

_supabase_client: Client | None = None


class NotAuthenticated(Exception):
    """Raised by get_current_account when there's no valid session."""


def _check_ascii(name: str, value: str) -> None:
    """HTTP headers must be ASCII. A stray character pasted into a hosting
    dashboard (curly quote, invisible space, etc.) breaks the Supabase client
    with a UnicodeEncodeError that looks unrelated to the real cause. Catch
    it here with a precise report instead of a mystery crash deep in httpx."""
    try:
        value.encode("ascii")
    except UnicodeEncodeError as e:
        bad_char = value[e.start]
        log.error(
            "%s has a non-ASCII character at position %d (codepoint U+%04X). "
            "length=%d. This is almost always a stray character introduced "
            "when pasting into a dashboard — delete and re-paste the value.",
            name, e.start, ord(bad_char), len(value),
        )
        raise


def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        config.require("SUPABASE_URL", "SUPABASE_ANON_KEY")
        _check_ascii("SUPABASE_URL", config.SUPABASE_URL)
        _check_ascii("SUPABASE_ANON_KEY", config.SUPABASE_ANON_KEY)
        _supabase_client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    return _supabase_client


def sign_up(email: str, password: str) -> str:
    """Create a Supabase Auth user. Returns their user id. Raises on failure
    (e.g. email already registered, weak password) — caller shows the error."""
    resp = _get_supabase().auth.sign_up({"email": email, "password": password})
    if resp.user is None:
        raise ValueError("Signup failed — check the email/password and try again.")
    return resp.user.id


def _raw_sign_in_diagnostic(email: str, password: str) -> None:
    """Bypass the supabase-py client entirely and hit Supabase's REST auth
    endpoint directly with httpx, logging the *raw* status/body byte-safely.
    Ground truth when the client library's own exception formatting is
    itself throwing (mystery UnicodeEncodeErrors with no useful message)."""
    try:
        r = httpx.post(
            f"{config.SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": config.SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=15,
        )
        safe_body = r.text.encode("ascii", errors="backslashreplace").decode("ascii")[:500]
        log.error("RAW auth diagnostic: status=%d body=%s", r.status_code, safe_body)
    except Exception as diag_e:  # noqa: BLE001 - this IS the diagnostic, must not itself crash silently
        log.error("RAW auth diagnostic itself failed: %s: %s", type(diag_e).__name__, repr(diag_e))


def sign_in(email: str, password: str) -> str:
    """Verify credentials against Supabase Auth. Returns the user id, or
    raises on invalid credentials."""
    try:
        resp = _get_supabase().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception:
        _raw_sign_in_diagnostic(email, password)
        raise
    if resp.user is None:
        raise ValueError("Invalid email or password.")
    return resp.user.id


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.SESSION_SECRET, salt=_SALT)


def make_session_cookie_value(user_id: str, account_id: str) -> str:
    return _serializer().dumps({"user_id": user_id, "account_id": account_id})


def read_session_cookie(value: str) -> dict | None:
    try:
        return _serializer().loads(value, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_account(request: Request) -> dict:
    """FastAPI dependency: the logged-in user's account, or raise NotAuthenticated."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        raise NotAuthenticated("No session cookie")

    session_data = read_session_cookie(raw)
    if session_data is None:
        raise NotAuthenticated("Invalid or expired session")

    account = db.get_account_by_id(session_data["account_id"])
    if account is None:
        raise NotAuthenticated("Account no longer exists")
    return account
