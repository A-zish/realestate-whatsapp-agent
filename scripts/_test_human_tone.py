"""Simulate the brush-off scenario from the screenshot and check for repeated
stock phrases across turns (the tell-tale robotic pattern being fixed)."""
import json
import sys

from app import agent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

lead = {"phone": "+910000000002", "name": "Tester", "history_json": ""}
turns = [
    "hi",
    "3BHK in Vaishali Nagar",
    "show me",
    "Not now",
    "Not sure",
    "Just looking",
]

replies = []
for msg in turns:
    action = agent.run_agent(lead, msg)
    reply = action["reply_text"]
    replies.append(reply)
    print(f"USER: {msg}\nBOT : {reply}\n")
    lead["history_json"] = json.dumps(action["_history"])

# Check for exact-duplicate bot replies (the robotic tell from the screenshot)
dupes = [r for r in set(replies) if replies.count(r) > 1]
print("Exact duplicate bot replies:", dupes if dupes else "NONE (good)")

banned_phrases = ["no worries, we'll keep the option open", "feel free to reach out"]
hits = [p for r in replies for p in banned_phrases if p in r.lower()]
print("Banned stock phrases found:", hits if hits else "NONE (good)")
