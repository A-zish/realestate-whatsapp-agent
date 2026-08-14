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


def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        config.require("SUPABASE_URL", "SUPABASE_ANON_KEY")
        _supabase_client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    return _supabase_client


def sign_up(email: str, password: str) -> str:
    """Create a Supabase Auth user. Returns their user id. Raises on failure
    (e.g. email already registered, weak password) — caller shows the error."""
    resp = _get_supabase().auth.sign_up({"email": email, "password": password})
    if resp.user is None:
        raise ValueError("Signup failed — check the email/password and try again.")
    return resp.user.id


def sign_in(email: str, password: str) -> str:
    """Verify credentials against Supabase Auth. Returns the user id, or
    raises on invalid credentials."""
    resp = _get_supabase().auth.sign_in_with_password(
        {"email": email, "password": password}
    )
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
