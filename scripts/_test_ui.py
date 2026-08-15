"""Verify every dashboard page renders with the new design system."""
import sys

from fastapi.testclient import TestClient

from app.main import app

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)

# Auth pages render standalone
for path, marker in [("/login", "Welcome back"), ("/signup", "Create your account")]:
    r = c.get(path)
    print(f"{path}: {r.status_code} | has design system: {'app.css' in r.text} | marker: {marker in r.text}")
    assert r.status_code == 200 and "app.css" in r.text and marker in r.text

# Static assets are served
for asset in ["/static/css/app.css", "/static/js/app.js"]:
    r = c.get(asset)
    print(f"{asset}: {r.status_code} ({len(r.content)} bytes)")
    assert r.status_code == 200

# Log in, then check every dashboard page
r = c.post("/login", data={"email": "adashishdwivedi07@gmail.com", "password": "RamaOwner!2026"},
           follow_redirects=False)
assert r.status_code == 303, f"login failed: {r.status_code}"
print("login: OK")

checks = [
    ("/dashboard", ["Overview", "Total leads", "stat-value", "Bring in leads"]),
    # Either a populated table or the empty state is valid depending on data.
    ("/dashboard/leads", ["Leads", "Search name"]),
    ("/dashboard/properties", ["Property inventory", "Add a property", "Select type"]),
    ("/dashboard/playground", ["Test your AI agent", "Sandbox", "Playground vs"]),
    ("/dashboard/settings", ["Agent &amp; branding", "Custom instructions", "lead link"]),
]
for path, markers in checks:
    r = c.get(path)
    missing = [m for m in markers if m not in r.text]
    print(f"{path}: {r.status_code} | sidebar: {'nav-item' in r.text} | missing: {missing or 'none'}")
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert not missing, f"{path} missing {missing}"

# Filters on the leads page
r = c.get("/dashboard/leads?score=HOT")
print("/dashboard/leads?score=HOT:", r.status_code)
assert r.status_code == 200

# Root redirects to login
r = c.get("/", follow_redirects=False)
print("/ redirect:", r.status_code, r.headers.get("location"))
assert r.status_code == 307

print("\nUI RENDER TEST PASSED")
