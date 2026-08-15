"""End-to-end: upload a spreadsheet -> preview -> import -> leads exist,
plus the WhatsApp connect screen and encrypted credential storage."""
import io
import sys

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import crypto, db
from app.main import app

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)
r = c.post("/login", data={"email": "adashishdwivedi07@gmail.com", "password": "RamaOwner!2026"},
           follow_redirects=False)
assert r.status_code == 303, "login failed"
account = db.get_account_by_slug("rama-realestate")
print("logged in as:", account["agency_name"])

# --- crypto round trip ---
enc = crypto.encrypt("super-secret-token")
print("encrypted looks like:", enc[:24] + "…")
assert crypto.decrypt(enc) == "super-secret-token"
assert "super-secret-token" not in enc, "plaintext must not appear in ciphertext"
print("encryption round trip: OK")

# --- build an xlsx with the real demo numbers ---
wb = Workbook(); ws = wb.active
ws.append(["Name", "Mobile Number"])
ws.append(["maviya", "7891323775"])
ws.append(["Ashish", "8209727324"])
ws.append(["Dushyant", "8239819100"])
ws.append(["Bad Row", ""])
buf = io.BytesIO(); wb.save(buf)

# --- preview (nothing saved yet) ---
before = len(db.get_all_leads(account["id"]))
r = c.post("/dashboard/import",
           files={"file": ("demo_leads.xlsx", buf.getvalue(),
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
print("preview page:", r.status_code, "| shows all 3:",
      all(n in r.text for n in ["maviya", "Ashish", "Dushyant"]))
assert r.status_code == 200
after_preview = len(db.get_all_leads(account["id"]))
print(f"leads before={before} after preview={after_preview} (preview must not save):",
      before == after_preview)
assert before == after_preview, "preview must not write to the DB!"

# --- confirm the import ---
r = c.post("/dashboard/import/confirm", json={"leads": [
    {"name": "maviya", "phone": "+917891323775"},
    {"name": "Ashish", "phone": "+918209727324"},
    {"name": "Dushyant", "phone": "+918239819100"},
]})
print("import confirm:", r.status_code, r.json())
assert r.status_code == 200

leads = db.get_all_leads(account["id"])
imported = {l["phone"]: l for l in leads}
for phone, name in [("+917891323775", "maviya"), ("+918209727324", "Ashish"),
                    ("+918239819100", "Dushyant")]:
    assert phone in imported, f"{name} not imported"
    print(f"  ✓ {name} {phone} status={imported[phone]['status']} source={imported[phone]['source']}")

# --- re-import must update, not duplicate ---
r = c.post("/dashboard/import/confirm", json={"leads": [{"name": "maviya", "phone": "+917891323775"}]})
print("re-import (should be 0 created, 1 updated):", r.json())
assert r.json()["created"] == 0 and r.json()["updated"] == 1

# --- WhatsApp page renders ---
r = c.get("/dashboard/whatsapp")
print("whatsapp page:", r.status_code, "| explains requirements:",
      "Business verification" in r.text and "24-hour" in r.text)
assert r.status_code == 200

# --- import page renders ---
r = c.get("/dashboard/import")
print("import page:", r.status_code)
assert r.status_code == 200

print("\nIMPORT + WHATSAPP TEST PASSED")
