"""Phase 3: send the opening WhatsApp message to every new lead.

Usage:
    python -m scripts.send_openers              # all status=new leads
    python -m scripts.send_openers +9198XXXXXX  # only this phone (for testing)

For each targeted lead with status == 'new', sends the opener and flips the
status to 'contacted'. Failures (e.g. a number that hasn't joined the Twilio
sandbox) are logged and the lead is left as 'new' so it can be retried.

NOTE: This opener is sent as free-form text, which works in the Twilio sandbox.
In PRODUCTION (Meta Cloud API), a business-initiated first message to a lead who
has not yet replied MUST be a PRE-APPROVED TEMPLATE message — free-form text will
be rejected outside the 24-hour customer-service window.
"""
import sys

from app import config
from app.messages import OPENER_TEMPLATE as OPENER
from app.sheets import get_all_leads, update_lead_fields
from app.twilio_client import send_whatsapp


def send_openers(only_phone: str | None = None) -> None:
    leads = get_all_leads()
    sent = skipped = failed = 0

    for lead in leads:
        phone = lead.get("phone", "").strip()
        if not phone:
            continue
        if only_phone and phone != only_phone:
            continue
        if lead.get("status") != "new":
            skipped += 1
            continue

        name = lead.get("name") or "there"
        body = OPENER.format(name=name, builder=config.BUILDER_NAME)
        try:
            send_whatsapp(phone, body)
            update_lead_fields(phone, {"status": "contacted"})
            print(f"  sent -> {phone} ({name})")
            sent += 1
        except Exception as e:  # noqa: BLE001 - log and continue to next lead
            print(f"  FAILED -> {phone} ({name}): {e}")
            failed += 1

    print(f"\nDone. sent={sent} skipped(not new)={skipped} failed={failed}")


def main() -> None:
    only_phone = sys.argv[1] if len(sys.argv) > 1 else None
    if only_phone:
        from app.utils import normalize_phone

        only_phone = normalize_phone(only_phone)
        print(f"Sending opener only to {only_phone}")
    else:
        print("Sending openers to ALL status=new leads")
    send_openers(only_phone)


if __name__ == "__main__":
    main()
