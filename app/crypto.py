"""Symmetric encryption for third-party credentials stored at rest.

Agencies hand us their own Twilio auth token so their AI agent can send from
their WhatsApp number. That's someone else's credential, so it never sits in
the database in plaintext — it's Fernet-encrypted (AES-128-CBC + HMAC) with a
key that lives only in the environment.

If ENCRYPTION_KEY is ever rotated, previously stored tokens become
undecryptable and each agency has to re-enter theirs — decrypt() returns None
rather than raising so the app degrades to "not connected" instead of 500ing.
"""
import logging

from cryptography.fernet import Fernet, InvalidToken

from app import config

log = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        config.require("ENCRYPTION_KEY")
        _fernet = Fernet(config.ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Return the plaintext, or None if it can't be decrypted (wrong/rotated key)."""
    if not ciphertext:
        return None
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as e:
        log.error("Could not decrypt stored credential: %s", e)
        return None
