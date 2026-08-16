"""Sending WhatsApp messages via Twilio, per agency.

Each account can connect their own Twilio credentials (see the Connect
WhatsApp screen). When they have, we send as them. When they haven't, we fall
back to the platform's shared sandbox credentials — good enough for demos,
but the sandbox will only deliver to numbers that have sent it the join code.
"""
import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app import config, db

log = logging.getLogger(__name__)

_platform_client: Client | None = None


class WhatsAppNotConfigured(Exception):
    """No usable Twilio credentials for this account."""


def _to_whatsapp(number: str) -> str:
    number = (number or "").strip()
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def _get_platform_client() -> Client:
    global _platform_client
    if _platform_client is None:
        config.require("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
        _platform_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _platform_client


def get_sender(account: dict, *, own_only: bool = False) -> tuple[Client, str]:
    """Return (client, from_number) for this account.

    Prefers the agency's own Twilio credentials. Platform sandbox is only used
    when own_only is False (inbound webhook / test). Openers must pass
    own_only=True so a second tenant never rides the shared number.
    """
    creds = db.get_whatsapp_credentials(account["id"])
    if creds:
        from_number = creds["whatsapp_from"] or config.TWILIO_WHATSAPP_FROM
        return Client(creds["account_sid"], creds["auth_token"]), _to_whatsapp(from_number)

    if own_only:
        raise WhatsAppNotConfigured(
            "Connect this agency's own WhatsApp number before sending openers."
        )

    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        raise WhatsAppNotConfigured(
            "No WhatsApp credentials — connect your Twilio account in Settings."
        )
    from_number = account.get("twilio_whatsapp_from") or config.TWILIO_WHATSAPP_FROM
    return _get_platform_client(), _to_whatsapp(from_number)


def send_whatsapp(
    account: dict,
    to: str,
    body: str,
    media_urls: list[str] | None = None,
    *,
    own_only: bool = False,
) -> str:
    """Send one WhatsApp message as this account. Returns the Twilio message SID."""
    client, from_number = get_sender(account, own_only=own_only)
    kwargs = {"from_": from_number, "to": _to_whatsapp(to), "body": body}
    if media_urls:
        kwargs["media_url"] = media_urls

    message = client.messages.create(**kwargs)
    log.info("Sent WhatsApp to %s as %s (sid=%s)", to, account.get("slug"), message.sid)
    return message.sid


def friendly_error(exc: Exception) -> str:
    """Turn a Twilio failure into something an agency owner can act on.

    Twilio's raw messages are written for developers; the sandbox-membership
    error in particular is the single most common thing an agency will hit,
    and the raw text doesn't explain what to do about it.
    """
    if isinstance(exc, WhatsAppNotConfigured):
        return str(exc)
    if isinstance(exc, TwilioRestException):
        code = exc.code
        if code == 63007:
            return "This number hasn't joined your WhatsApp sandbox yet — ask them to send the join code first."
        if code == 21608:
            return "Sandbox can only message numbers that sent the join code. Ask them to join, or connect a verified WhatsApp Business number."
        if code == 21211:
            return "That phone number looks invalid."
        if code in (20003, 20005):
            return "Twilio rejected the credentials — check your Account SID and Auth Token."
        if code == 63016:
            return "Outside the 24-hour window, WhatsApp requires a pre-approved template message."
        return f"Twilio error {code}: {exc.msg}"
    return str(exc)
