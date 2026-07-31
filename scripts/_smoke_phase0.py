"""Phase 0 self-test: exercise /health and /webhook without a live server."""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

h = c.get("/health")
print("HEALTH", h.status_code, h.json())

r = c.post("/webhook", data={"From": "whatsapp:+919812345678", "Body": "Hi there"})
print("WEBHOOK", r.status_code, r.headers.get("content-type"))
print(r.text)

assert h.status_code == 200
assert r.status_code == 200
assert "Got your message!" in r.text
print("PHASE 0 SMOKE TEST PASSED")
