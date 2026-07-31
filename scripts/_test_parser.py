"""Quick check that the agent's JSON parser tolerates fenced / messy output."""
from app.agent import _parse_json

cases = [
    '{"reply_text":"hi","score":null}',
    '```json\n{"reply_text":"hello","send_photo_url":null}\n```',
    'Sure! {"reply_text":"ok","status":"qualifying"} hope that helps',
    '```\n{"reply_text":"plain fence"}\n```',
]
for c in cases:
    out = _parse_json(c)
    print("OK ->", out)
print("PARSER TESTS PASSED")
