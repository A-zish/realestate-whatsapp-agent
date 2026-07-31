"""Confirm the agent (and /demo endpoints) surface quick_replies chips."""
import sys

from fastapi.testclient import TestClient

from app import sheets
from app.main import app
from app.utils import web_session_phone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

c = TestClient(app)
session_id = "test-session-chips-001"
phone = web_session_phone(session_id)

r = c.post("/demo/start", json={"session_id": session_id, "name": "Chip Tester"})
data = r.json()
print("start quick_replies:", data.get("quick_replies"))
assert data.get("quick_replies") == ["YES"]

r = c.post("/demo/chat", json={"session_id": session_id, "name": "Chip Tester", "message": "YES"})
data = r.json()
print(f"BOT: {data['reply_text']}\nquick_replies: {data.get('quick_replies')}")

# cleanup
ws = sheets._get_worksheet()
vals = ws.get_all_values()
for i in range(len(vals) - 1, 0, -1):
    if vals[i] and vals[i][0] == phone:
        ws.delete_rows(i + 1)
print("cleaned test lead")

print("\nQUICK REPLIES TEST DONE")
