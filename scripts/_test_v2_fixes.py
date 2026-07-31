"""Verify: (1) the first 'what type' question offers a broad canonical set of
quick_replies, not just what's in the narrow demo inventory, and (2) a
persuasion question ('why should I buy it') does NOT resend a photo."""
import json
import sys

from app import agent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

lead = {"phone": "+910000000003", "name": "Tester", "history_json": ""}

turns = [
    "hi, looking to buy a property",   # -> should offer broad type quick_replies
    "3BHK",
    "Vaishali Nagar please",
    "show me",                          # -> should send media
    "why should i buy it",              # -> should NOT resend media
]

for msg in turns:
    action = agent.run_agent(lead, msg)
    print(f"USER: {msg}")
    print(f"BOT : {action['reply_text']}")
    print(f"  media={action['send_media_urls']}  quick_replies={action['quick_replies']}\n")
    lead["history_json"] = json.dumps(action["_history"])

print("Check above: turn 1 quick_replies should be a broad canonical set")
print("(Flat/Villa/Plot/Commercial/Farmhouse-ish), and the last turn's media should be [].")
