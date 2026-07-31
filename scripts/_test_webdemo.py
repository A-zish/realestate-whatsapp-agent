"""Test the web-chat demo pipeline end to end: start -> chat turns -> history."""
import sys

from fastapi.testclient import TestClient

from app import config, sheets
from app.main import app
from app.utils import web_session_phone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)
session_id = "test-session-webdemo-001"
phone = web_session_phone(session_id)
print("synthetic phone:", phone)

# 1. Unauthenticated demo page loads
r = c.get("/demo")
print("GET /demo:", r.status_code, "OK" if "Rama RealEstate" in r.text or config.BUILDER_NAME in r.text else "MISSING BUILDER NAME")

# 2. Start the chat
r = c.post("/demo/start", json={"session_id": session_id, "name": "Test Visitor"})
print("POST /demo/start:", r.status_code, r.json())

# 3. Confirm lead was created with source=web-demo and synthetic phone
lead = sheets.get_lead(phone)
assert lead is not None, "lead not created"
print("lead after start:", {k: lead[k] for k in ("phone", "name", "source", "status")})
assert lead["source"] == "web-demo"
assert lead["phone"] == phone

# 4. Send a couple of chat turns through the real agent
for msg in ["YES", "Looking for a 2BHK in Mansarovar, budget 45 lakh"]:
    r = c.post("/demo/chat", json={"session_id": session_id, "name": "Test Visitor", "message": msg})
    data = r.json()
    print(f"USER: {msg}\nBOT : {data['reply_text']}  photo={data.get('photo_url')}\n")

# 5. History endpoint reconstructs the transcript
r = c.get(f"/demo/history?session_id={session_id}")
hist = r.json()
print("history exists:", hist["exists"], "turns:", len(hist["history"]))
assert hist["exists"] and len(hist["history"]) >= 4

# 6. Admin dashboard shows this lead (auth required)
r = c.get("/admin/leads")
print("GET /admin/leads no-auth:", r.status_code)
assert r.status_code == 401
r = c.get("/admin/leads", auth=(config.ADMIN_USER, config.ADMIN_PASSWORD))
print("GET /admin/leads with-auth:", r.status_code, "contains phone:", phone in r.text)
assert r.status_code == 200 and phone in r.text

print("\nWEB DEMO PIPELINE TEST PASSED")
