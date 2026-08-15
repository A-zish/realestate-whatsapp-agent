"""Auth: self-hosted, standard-library only.

Passwords are hashed with PBKDF2-HMAC-SHA256 (the same primitive Django and
Werkzeug use by default) and verified in constant time. Sessions are a signed
cookie (itsdangerous) holding {user_id, account_id}, valid ~7 days.

Why not an external auth service: we tried one and it cost us three separate
production failures — email-confirmation friction on every signup, a signup
rate limit, and an opaque UnicodeEncodeError inside the client library that
only reproduced on the host. None of that buys anything here: hashing a
password is a solved stdlib problem with no network hop and identical
behaviour locally and in production.

FastAPI usage:
    @app.get("/dashboard")
    def dashboard(account: dict = Depends(get_current_account)): ...

Unauthenticated access raises NotAuthenticated, which app/main.py turns into
a redirect to /login via a registered exception handler.
"""
import hashlib
import hmac
import logging
import secrets

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import config, db

log = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days
_SALT = "realestate-saas-session"

# OWASP-recommended floor for PBKDF2-HMAC-SHA256 (2023 guidance).
_PBKDF2_ITERATIONS = 600_000
_HASH_PREFIX = "pbkdf2_sha256"


class NotAuthenticated(Exception):
    """Raised by get_current_account when there's no valid session."""


class AuthError(Exception):
    """Signup/login failed for a reason we can safely show the user."""


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Return a self-describing hash string: algo$iterations$salt_hex$hash_hex.

    Storing the parameters alongside the hash means the iteration count can be
    raised later without invalidating existing passwords.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_HASH_PREFIX}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify against a hash produced by hash_password."""
    try:
        prefix, iterations_s, salt_hex, hash_hex = stored.split("$")
        if prefix != _HASH_PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_s)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def sign_up(email: str, password: str, account_id) -> str:
    """Create a login for an account. Returns the new user id."""
    email = normalize_email(email)
    if len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")
    if db.get_user_by_email(email) is not None:
        raise AuthError("That email is already registered.")
    user = db.create_user(email, hash_password(password), account_id)
    log.info("Created login %s for account %s", email, account_id)
    return user["id"]


def sign_in(email: str, password: str) -> str:
    """Verify credentials. Returns the user id, or raises AuthError."""
    user = db.get_user_by_email(normalize_email(email))
    if user is None or not verify_password(password, user["password_hash"]):
        raise AuthError("Invalid email or password.")
    return user["id"]


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
