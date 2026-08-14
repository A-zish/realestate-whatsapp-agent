"""Smoke test for routes that don't require a live database connection:
health check, and the auth-redirect for protected pages when logged out."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

h = c.get("/health")
print("GET /health:", h.status_code, h.json())
assert h.status_code == 200 and h.json() == {"status": "ok"}

# No session cookie -> NotAuthenticated -> redirected to /login
d = c.get("/dashboard", follow_redirects=False)
print("GET /dashboard (no cookie):", d.status_code, d.headers.get("location"))
assert d.status_code == 303 and d.headers.get("location") == "/login"

p = c.get("/dashboard/properties", follow_redirects=False)
print("GET /dashboard/properties (no cookie):", p.status_code, p.headers.get("location"))
assert p.status_code == 303

s = c.get("/dashboard/settings", follow_redirects=False)
print("GET /dashboard/settings (no cookie):", s.status_code, s.headers.get("location"))
assert s.status_code == 303

# Static pages that need no DB
signup = c.get("/signup")
print("GET /signup:", signup.status_code, "has form:" , "action=\"/signup\"" in signup.text)
assert signup.status_code == 200

login = c.get("/login")
print("GET /login:", login.status_code, "has form:", "action=\"/login\"" in login.text)
assert login.status_code == 200

print("\nSAAS WIRING SMOKE TEST PASSED (routes not requiring live DB)")
