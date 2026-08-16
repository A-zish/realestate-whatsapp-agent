"""Twilio request signature check for /webhook."""
from __future__ import annotations

import logging

from fastapi import Request
from twilio.request_validator import RequestValidator

from app import config, db

log = logging.getLogger(__name__)


def _webhook_url(request: Request) -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL.rstrip("/") + request.url.path
    return str(request.url)


def verify_twilio_signature(request: Request, params: dict[str, str]) -> bool:
    """True if X-Twilio-Signature matches the account (or platform) auth token."""
    signature = request.headers.get("X-Twilio-Signature") or ""
    if not signature:
        log.warning("Twilio webhook missing X-Twilio-Signature")
        return False

    to_number = params.get("To") or ""
    account = db.get_account_by_twilio_number(to_number) if to_number else None
    tokens: list[str] = []
    if account:
        creds = db.get_whatsapp_credentials(account["id"])
        if creds and creds.get("auth_token"):
            tokens.append(creds["auth_token"])
    if config.TWILIO_AUTH_TOKEN:
        tokens.append(config.TWILIO_AUTH_TOKEN)

    if not tokens:
        log.error("No Twilio auth token available to validate webhook")
        return False

    url = _webhook_url(request)
    for token in tokens:
        if RequestValidator(token).validate(url, params, signature):
            return True
    log.warning("Twilio signature mismatch for To=%s url=%s", to_number, url)
    return False
