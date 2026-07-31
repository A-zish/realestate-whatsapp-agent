"""Test the admin multi-file property-upload pipeline end to end."""
import base64
import sys

from fastapi.testclient import TestClient

from app import config, sheets, utils
from app.main import app

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)
auth = (config.ADMIN_USER, config.ADMIN_PASSWORD)

# a 1x1 PNG (used twice to simulate multiple photos)
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

r = c.post(
    "/admin/properties",
    auth=auth,
    data={
        "title": "Admin Test Flat, Jagatpura",
        "type": "3BHK",
        "location": "Jagatpura, Jaipur",
        "price": "60 lakh",
        "available": "yes",
    },
    files=[
        ("photos", ("test1.png", png, "image/png")),
        ("photos", ("test2.png", png, "image/png")),
    ],
    follow_redirects=False,
)
print("POST status (303 = ok):", r.status_code)

props = sheets.get_properties(use_cache=False, only_available=False)
match = [p for p in props if "Admin Test" in p.get("title", "")]
print("rows added:", len(match))
media_list = match[-1]["media"] if match else []
print("stored media list:", media_list)
assert len(media_list) == 2, f"expected 2 media items, got {media_list}"

# confirm each saved file is served at /media/<file>
for rel in media_list:
    served = c.get("/" + rel)
    print(f"served {rel}: {served.status_code} {served.headers.get('content-type')}")
    assert served.status_code == 200

print("public URLs Twilio would fetch:", [utils.resolve_media_url(u) for u in media_list])

assert r.status_code == 303
print("\nMULTI-FILE UPLOAD PIPELINE TEST PASSED")
