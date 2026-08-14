"""Verify property photo upload lands in Supabase Storage (not local disk)
and is served back as a persistent public URL."""
import base64
import sys

from fastapi.testclient import TestClient

from app import db
from app.main import app

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)
r = c.post("/login", data={"email": "owner@skylineestates.com", "password": "Skyline!2026"})
cookies = r.cookies if r.status_code in (200, 303) else c.cookies

png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

r = c.post(
    "/dashboard/properties",
    cookies=cookies,
    data={"title": "Skyline Test Flat", "type": "2BHK", "location": "Bandra", "price": "80 lakh", "available": "yes"},
    files={"photos": ("test.png", png, "image/png")},
    follow_redirects=False,
)
print("upload POST status:", r.status_code)
assert r.status_code == 303

account = db.get_account_by_slug("skyline-estates")
props = db.get_properties(account["id"], only_available=False)
match = [p for p in props if p["title"] == "Skyline Test Flat"]
print("property found:", len(match) == 1)
media = match[0]["media"] if match else []
print("media urls:", media)
assert media and media[0].startswith("https://"), "expected a Supabase Storage public URL"
assert "supabase.co/storage" in media[0], f"unexpected URL host: {media[0]}"

import httpx
resp = httpx.get(media[0], timeout=15)
print("public fetch status:", resp.status_code, resp.headers.get("content-type"))
assert resp.status_code == 200

print("\nSTORAGE UPLOAD TEST PASSED")
