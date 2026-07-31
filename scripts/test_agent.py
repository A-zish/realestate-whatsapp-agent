"""Offline Phase 4 test: simulate a multi-turn conversation with the agent.

Calls the LLM directly (no Twilio, no phone) so we can confirm Groq returns
valid JSON and the agent asks sensible questions, extracts fields, offers a
photo, and books a visit. Does NOT touch the Google Sheet.

Usage:
    python -m scripts.test_agent
"""
import json
import sys

from app import agent

# Windows consoles default to cp1252 and can't print ₹/emoji; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPTED_USER_TURNS = [
    "YES",
    "I'm looking in Mansarovar, Jaipur",
    "A 2BHK apartment",
    "budget around 45 lakh",
    "show me the property",
    "looks good, I want to book a site visit this week",
]


def main() -> None:
    lead = {"phone": "+910000000000", "name": "Tester", "history_json": ""}

    for i, user_msg in enumerate(SCRIPTED_USER_TURNS, 1):
        print(f"\n--- Turn {i} ---")
        print(f"USER: {user_msg}")
        action = agent.run_agent(lead, user_msg)

        print(f"BOT : {action.get('reply_text')}")
        if action.get("send_media_urls"):
            print(f"MEDIA: {action['send_media_urls']}")
        print(
            "  [extracted]",
            {k: v for k, v in (action.get("extracted") or {}).items() if v},
        )
        print(f"  [status={action.get('status')} score={action.get('score')} "
              f"stage={action.get('stage')}]")

        # Carry the updated history forward, like the webhook does.
        lead["history_json"] = json.dumps(action.get("_history", []))

    print("\nAGENT TEST COMPLETE")


if __name__ == "__main__":
    main()
