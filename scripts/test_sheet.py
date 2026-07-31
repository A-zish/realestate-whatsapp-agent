"""Phase 1 test: write, read, and update a dummy lead in the Google Sheet.

Usage:
    python -m scripts.test_sheet

Requires GOOGLE_SHEET_ID and a valid service-account JSON (see .env), and the
sheet must be shared with the service account's email (Editor).
"""
from app.sheets import get_lead, update_lead_fields, upsert_lead

DUMMY_PHONE = "+919999000011"


def main() -> None:
    print("1) Upserting dummy lead...")
    upsert_lead(
        {
            "phone": DUMMY_PHONE,
            "name": "Test Lead",
            "source": "phase1-test",
            "status": "new",
        }
    )

    print("2) Reading it back...")
    lead = get_lead(DUMMY_PHONE)
    assert lead is not None, "Lead not found after upsert!"
    assert lead["name"] == "Test Lead", lead
    print("   read:", {k: lead[k] for k in ("phone", "name", "source", "status")})

    print("3) Updating a couple of fields...")
    update_lead_fields(
        DUMMY_PHONE, {"status": "qualifying", "budget": "50L", "score": "WARM"}
    )
    lead = get_lead(DUMMY_PHONE)
    assert lead["status"] == "qualifying" and lead["budget"] == "50L", lead
    print("   updated:", {k: lead[k] for k in ("status", "budget", "score")})

    print("\nPHASE 1 SHEET TEST PASSED  (you can delete the test row from the sheet)")


if __name__ == "__main__":
    main()
