"""Send one WhatsApp message via Twilio — Phase 0 smoke test.

Usage:
    python -m scripts.send_test +9198XXXXXXXX
    python -m scripts.send_test +9198XXXXXXXX "Custom message text"

NOTE: In the Twilio WhatsApp sandbox you can only freely message a number
*after* it has sent the sandbox join code ("join <two-words>") to the sandbox
number. Send to your own joined phone for testing.
"""
import sys

from app import config
from app.twilio_client import send_whatsapp


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    to = sys.argv[1]
    body = sys.argv[2] if len(sys.argv) > 2 else (
        f"Hello from {config.BUILDER_NAME}! This is a Twilio sandbox test."
    )

    sid = send_whatsapp(to, body)
    print(f"Sent. Twilio message SID: {sid}")


if __name__ == "__main__":
    main()
