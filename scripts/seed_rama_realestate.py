"""Seed the first tenant (Rama RealEstate) into Postgres — one-time setup.

Creates the `accounts` row (idempotent — safe to re-run), links the existing
shared Twilio sandbox number to it so /webhook keeps working unchanged, adds
a login for the dashboard, and seeds the 3 demo properties from
data/properties.json.

Usage:
    python -m scripts.seed_rama_realestate <email> <password>

NOTE: if your Supabase project has "Confirm email" enabled (Authentication
-> Settings), you'll need to click the confirmation link Supabase emails to
<email> before you can log in with it.
"""
import json
import os
import sys

from app import auth, config, db

_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "properties.json")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    email, password = sys.argv[1], sys.argv[2]

    account = db.get_account_by_slug("rama-realestate")
    if account is None:
        account = db.create_account(agency_name="Rama RealEstate", agent_name="Priya", city="Jaipur")
        print(f"Created account: {account['slug']} ({account['id']})")
    else:
        print(f"Account already exists: {account['slug']} ({account['id']})")

    if config.TWILIO_WHATSAPP_FROM and not account.get("twilio_whatsapp_from"):
        db.update_account(account["id"], {"twilio_whatsapp_from": config.TWILIO_WHATSAPP_FROM})
        print(f"Linked WhatsApp number: {config.TWILIO_WHATSAPP_FROM}")

    try:
        user_id = auth.sign_up(email, password)
        db.link_user_to_account(user_id, account["id"])
        print(f"Created login for {email} -> account {account['slug']}")
    except Exception as e:  # noqa: BLE001 - likely "already registered", fine on re-run
        print(f"Signup skipped ({e}) — if this account exists, log in with it directly.")

    existing_props = db.get_properties(account["id"], only_available=False)
    if existing_props:
        print(f"Properties already seeded ({len(existing_props)}), skipping.")
    else:
        with open(_JSON, encoding="utf-8") as f:
            seed = json.load(f)
        for p in seed:
            db.add_property(
                account["id"],
                {
                    "title": p.get("title", ""),
                    "type": p.get("type", ""),
                    "location": p.get("location", ""),
                    "price": p.get("price", ""),
                    "media_urls": p.get("media_urls", []),
                    "available": "yes",
                },
            )
            print(f"  added property: {p.get('title')}")

    print(f"\nDone. Dashboard login: {email}")
    print(f"Web demo link: /demo/{account['slug']}")


if __name__ == "__main__":
    main()
