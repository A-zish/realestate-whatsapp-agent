"""Thin wrapper around the Twilio REST client for sending WhatsApp messages.

Phase 0 only needs `send_whatsapp`. The webhook itself replies via TwiML
(see app/main.py), which does not require these REST calls — but scripts and
later phases (sending openers, agent replies, media) use this helper.
"""
import logging

from twilio.rest import Client

from app import config

log = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """Lazily build a Twilio REST client from env credentials."""
    global _client
    if _client is None:
        config.require("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def _to_whatsapp(number: str) -> str:
    """Ensure a number carries the `whatsapp:` channel prefix."""
    number = number.strip()
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def send_whatsapp(to: str, body: str, media_url: str | None = None) -> str:
    """Send a WhatsApp message (optionally with one media attachment).

    `to` may be given with or without the `whatsapp:` prefix. Returns the
    Twilio message SID.
    """
    client = get_client()
    kwargs = {
        "from_": config.TWILIO_WHATSAPP_FROM,
        "to": _to_whatsapp(to),
        "body": body,
    }
    if media_url:
        kwargs["media_url"] = [media_url]

    message = client.messages.create(**kwargs)
    log.info("Sent WhatsApp to %s (sid=%s)", to, message.sid)
    return message.sid
