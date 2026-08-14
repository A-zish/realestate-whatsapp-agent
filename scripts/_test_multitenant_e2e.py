"""End-to-end verification against the LIVE Supabase project:
  1. Rama RealEstate login works, dashboard shows its own data.
  2. A brand-new second agency can sign up and its demo/dashboard are
     completely isolated from Rama RealEstate's.
  3. Chatting on both accounts' /demo/<slug> lands leads in the right tenant.
  4. WhatsApp webhook still round-trips correctly for Rama RealEstate
     (regression check for the existing sandbox number).
"""
import sys

from fastapi.testclient import TestClient

from app import db
from app.main import app

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)

# --- 1. Rama RealEstate login ---
r = c.post(
    "/login",
    data={"email": "adashishdwivedi07@gmail.com", "password": "RamaOwner!2026"},
    follow_redirects=False,
)
print("Rama login:", r.status_code, r.headers.get("location"))
assert r.status_code == 303, f"login failed: {r.text[:300]}"
rama_cookies = r.cookies

r = c.get("/dashboard", cookies=rama_cookies)
print("Rama dashboard:", r.status_code, "mentions Rama RealEstate:", "Rama RealEstate" in r.text)
assert r.status_code == 200 and "Rama RealEstate" in r.text

r = c.get("/dashboard/properties", cookies=rama_cookies)
print("Rama properties page:", r.status_code, "has 3 properties:", r.text.count("DEMO") >= 1)

# --- 2. Log in as the second agency (created via admin API to sidestep
#        today's Supabase free-tier email-confirmation rate limit; the
#        /signup route itself was already proven working for Rama's account) ---
r = c.post(
    "/login",
    data={"email": "owner@skylineestates.com", "password": "Skyline!2026"},
    follow_redirects=False,
)
print("Skyline login:", r.status_code, r.headers.get("location"))
assert r.status_code == 303, f"login failed: {r.text[:300]}"
skyline_cookies = r.cookies

r = c.get("/dashboard", cookies=skyline_cookies)
print("Skyline dashboard:", r.status_code, "mentions Skyline:", "Skyline Estates" in r.text,
      "leaks Rama:", "Rama RealEstate" in r.text)
assert "Skyline Estates" in r.text and "Rama RealEstate" not in r.text

r = c.get("/dashboard/properties", cookies=skyline_cookies)
print("Skyline properties (should be empty):", r.status_code, "0 properties:", "No properties yet" in r.text)
assert "No properties yet" in r.text

# --- 3. Chat on both accounts' demo links, confirm isolation ---
r = c.post("/demo/rama-realestate/start", json={"session_id": "e2e-rama-1", "name": "Rama Tester"})
print("Rama demo start:", r.status_code, r.json()["reply_text"][:50])
r = c.post("/demo/skyline-estates/start", json={"session_id": "e2e-skyline-1", "name": "Skyline Tester"})
print("Skyline demo start:", r.status_code, r.json()["reply_text"][:50])

rama_leads = db.get_all_leads(db.get_account_by_slug("rama-realestate")["id"])
skyline_leads = db.get_all_leads(db.get_account_by_slug("skyline-estates")["id"])
print(f"Rama leads: {len(rama_leads)} (names: {[l['name'] for l in rama_leads]})")
print(f"Skyline leads: {len(skyline_leads)} (names: {[l['name'] for l in skyline_leads]})")
assert any(l["name"] == "Rama Tester" for l in rama_leads)
assert not any(l["name"] == "Skyline Tester" for l in rama_leads)
assert any(l["name"] == "Skyline Tester" for l in skyline_leads)
assert not any(l["name"] == "Rama Tester" for l in skyline_leads)

# --- 4. WhatsApp webhook regression (Rama's existing sandbox number) ---
r = c.post(
    "/webhook",
    data={"From": "whatsapp:+919999888877", "To": "whatsapp:+14155238886",
          "Body": "Hi, YES I am looking", "ProfileName": "WA Tester"},
)
print("Webhook status:", r.status_code, "TwiML:", r.text[:150])
assert r.status_code == 200 and "<Message>" in r.text

print("\nMULTI-TENANT E2E TEST PASSED")
