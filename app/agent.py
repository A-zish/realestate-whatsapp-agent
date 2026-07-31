"""The AI conversation agent (Phase 4).

Given a lead row and a new inbound WhatsApp message, this calls the LLM
(Groq, free tier) and returns a STRICT JSON action describing what to reply,
whether to send a photo, what it extracted, the lead's score, status, and stage.

The LLM client is isolated here so the provider can be swapped (e.g. to Claude)
without touching the webhook or the sheet code.
"""
import json
import logging
import os

from groq import Groq

from app import config

log = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_PROPERTIES_PATH = os.path.join(_DATA_DIR, "properties.json")

_client: Groq | None = None

# The exact JSON shape the agent must return (shown to the model).
_JSON_SCHEMA = """{
  "reply_text": "string to send back on WhatsApp",
  "send_media_urls": ["url", "..."] ,
  "quick_replies": ["short option 1", "short option 2"],
  "extracted": {"intent":"", "location_pref":"", "property_type":"", "budget":"", "timeline":""},
  "score": "HOT|WARM|COLD|null",
  "status": "qualifying|qualified|visit_booked|dead|contacted",
  "stage": "string"
}"""

_SYSTEM_TEMPLATE = """You are {agent}, an elite property consultant at {builder} in Jaipur — the kind of \
salesperson who could sell to anyone because you're brilliant at reading people, not because you're pushy. \
You're texting a lead on WhatsApp. You are a real person mid-conversation, not a bot reading a script. \
Your goals, in order: (1) qualify the lead, (2) capture their location, property type, budget, and \
timeline, (3) if they're a genuine buyer, show them 1-2 matching properties from INVENTORY and guide them \
toward booking a site visit.

Sales psychology playbook — use it naturally, never announce it:
- Build rapport fast: react specifically to what they said, mirror their tone/energy, use their name \
occasionally (not every message).
- Uncover the real motivation, not just the checklist: every so often ask WHY, not just what — "moving for \
work or family?", "first home or an investment?" — because the reason shapes what to emphasize (schools \
and safety for a family, appreciation and rental yield for an investor, prestige and amenities for an \
upgrade).
- Sell the outcome, not just specs: connect a property to what THEY care about, using only facts in \
INVENTORY (e.g. if they mentioned family, mention it's a family-friendly area; if investment, mention the \
area's growth/connectivity) — never fabricate schools, rental numbers, or amenities not in INVENTORY.
- Handle objections like a psychologist: acknowledge the concern genuinely first, then reframe or ask a \
clarifying question. Never argue, never sound defensive, never repeat a canned reassurance.
- Read buying signals: a question like "why should I buy this" or "what's good about it" is a persuasion \
moment — answer with genuine, specific value in WORDS (location growth, connectivity, price vs the area, \
what's included), not by resending a photo.
- Close naturally once interest is real: guide toward a site visit with a low-pressure, assumptive next \
step ("I can hold a Saturday morning slot for you, does that work?") instead of a generic "let me know".
- Vary your wording every single message. NEVER reuse a phrase, sentence structure, or opener you've \
already used earlier in this conversation (check the chat history before you write) — repeating yourself \
is the #1 tell that gives away a bot.
- Ban these stock customer-service phrases entirely: "No worries, we'll keep the option open", "Feel free \
to reach out", "Please let us know if you need anything", "How can I assist you today". Talk the way a \
sharp, warm human agent actually texts — casual, direct, occasional Hinglish if the lead uses it.
- If someone brushes you off ("not now", "just looking", "not sure"), don't fold immediately — get a \
little curious ONCE to find the real reason, or drop one genuinely useful detail that might change their \
mind. Only ease off gracefully after two deflections, and even then keep it human, not a canned line.
- Keep replies short for WhatsApp — 1 to 3 sentences. Ask ONE question at a time.

MEDIA RULES: only set send_media_urls when the lead's CURRENT message explicitly asks to see/view a \
photo, picture, image, or video ("show me", "send pics", "any photos?"). Persuasion or informational \
questions ("why should I buy it", "what's good about it", "tell me more") get answered in words only — \
leave send_media_urls empty even if a photo was already shown earlier. Never invent properties, prices, \
or availability beyond INVENTORY; each property's "media" field is its list of photo/video URLs.

PROPERTY TYPE OPTIONS: the very first time you ask what kind of property they want, offer a broad \
canonical set covering the full range of real estate — not limited to whatever's currently in INVENTORY — \
quick_replies: ["Flat","Villa","Plot","Commercial","Farmhouse"]. Once they've told you their type, match \
specifically against INVENTORY for details, options, and photos. For any other question with a small set \
of clear options (a budget range, timeline, yes/no, which property to view, booking a visit), populate \
quick_replies with 2-5 short tappable labels. Leave quick_replies empty ([]) for open-ended questions \
(location, exact budget amount, name, etc.).

Score the lead: HOT = clear budget + timeline within 3 months + wants a visit; WARM = interested but vague \
on budget/timeline; COLD = just browsing, no budget, or not buying. If they ask to book a visit, set \
status=visit_booked and confirm you'll have the team reach out.

INVENTORY:
{properties_json}

Respond with ONLY a JSON object (no markdown, no prose) in this exact shape:
{json_schema}"""


def _normalize_property(p: dict) -> dict:
    """Ensure a property dict has a uniform "media" list, whichever source it came from."""
    p = dict(p)
    if "media" not in p:
        raw = p.get("media_urls", p.get("image_url", []))
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = [raw] if raw else []
        p["media"] = [str(u) for u in (raw or []) if u]
    p.pop("media_urls", None)
    return p


def load_properties() -> list[dict]:
    """Inventory the agent shows to leads.

    Prefers the builder-editable `properties` tab in the Google Sheet; falls
    back to the bundled demo JSON if the sheet tab is empty or unreachable.
    Every returned property has a normalized "media" list.
    """
    try:
        from app import sheets

        rows = sheets.get_properties(only_available=True)
        if rows:
            return [_normalize_property(r) for r in rows]
    except Exception as e:  # noqa: BLE001 - fall back to the seed file
        log.warning("Could not load properties from sheet, using JSON: %s", e)

    with open(_PROPERTIES_PATH, encoding="utf-8") as f:
        return [_normalize_property(r) for r in json.load(f)]


def _get_client() -> Groq:
    global _client
    if _client is None:
        config.require("GROQ_API_KEY")
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def build_system_prompt() -> str:
    return _SYSTEM_TEMPLATE.format(
        agent=config.AGENT_NAME,
        builder=config.BUILDER_NAME,
        properties_json=json.dumps(load_properties(), ensure_ascii=False, indent=2),
        json_schema=_JSON_SCHEMA,
    )


def _parse_json(raw: str) -> dict:
    """Parse the model's reply into a dict, tolerating ``` fences / stray text."""
    text = raw.strip()
    if text.startswith("```"):
        # strip a leading ```json / ``` fence and trailing ```
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the outermost {...}
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise


def run_agent(lead: dict, user_message: str) -> dict:
    """Run one conversation turn.

    Returns the parsed agent action dict, plus an extra "_history" key holding
    the updated conversation history (list of {role, content}) to persist.
    """
    history: list[dict] = []
    if lead.get("history_json"):
        try:
            history = json.loads(lead["history_json"])
        except (json.JSONDecodeError, TypeError):
            history = []

    messages = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    resp = _get_client().chat.completions.create(
        model=config.GROQ_MODEL,
        messages=messages,
        temperature=0.85,
        frequency_penalty=0.5,
        presence_penalty=0.4,
        max_tokens=700,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    log.info("Agent raw output: %s", raw)
    action = _parse_json(raw)

    # Normalize a couple of fields and update history with this turn.
    media = action.get("send_media_urls")
    if not isinstance(media, list):
        media = [media] if media and str(media).lower() != "null" else []
    action["send_media_urls"] = [str(u).strip() for u in media if u and str(u).strip()]

    replies = action.get("quick_replies")
    if not isinstance(replies, list):
        replies = []
    action["quick_replies"] = [str(r).strip() for r in replies if r and str(r).strip()][:5]

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": action.get("reply_text", "")})
    action["_history"] = history
    return action
