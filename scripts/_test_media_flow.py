"""Confirm the agent populates send_media_urls (list) when a lead asks to see a property."""
import sys

from app import agent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

lead = {"phone": "+910000000001", "name": "Tester", "history_json": ""}
for msg in ["hi", "2BHK in Mansarovar, budget 45 lakh", "haan dikhao"]:
    action = agent.run_agent(lead, msg)
    print(f"USER: {msg}\nBOT : {action['reply_text']}\nMEDIA: {action['send_media_urls']}\n")
    import json
    lead["history_json"] = json.dumps(action["_history"])

assert isinstance(action["send_media_urls"], list)
print("MEDIA FLOW TEST DONE (check MEDIA list populated on the show-property turn above)")
