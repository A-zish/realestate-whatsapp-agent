"""FastAPI app — Twilio WhatsApp webhook + web chat demo, both powered by the
same AI agent and Google Sheet (Phase 4 + v2 web demo).

Two front doors into the same conversation engine:
  - /webhook   Twilio posts inbound WhatsApp messages here (form-encoded).
  - /demo      A shareable, WhatsApp-styled browser chat — no WhatsApp/Twilio
               sandbox join needed. Same agent, same sheet, tagged
               source='web-demo' with a synthetic (non-dialable) phone key.

Inbound flow for either channel:
  1. Look up the lead by phone (create the row if unknown).
  2. Run the AI agent over the conversation history + the new message.
  3. Reply (TwiML for Twilio, JSON for the web demo), including a property
     photo if the agent chose one.
  4. Persist extracted fields, score, status, stage, last message, and the
     updated history back to the Google Sheet.
"""
import json
import logging
import os
import secrets
import time

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse

from app import agent, config, pages, sheets
from app.messages import OPENER_TEMPLATE
from app.utils import normalize_phone, resolve_media_url, web_session_phone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("realestate")

app = FastAPI(title="Real Estate WhatsApp Lead Agent")

# Folder where uploaded property photos live, served publicly at /media/<file>.
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "media")
os.makedirs(_MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=_MEDIA_DIR), name="media")

# Fields the agent extracts -> sheet columns. Only non-empty values overwrite.
_EXTRACT_FIELDS = ("intent", "location_pref", "property_type", "budget", "timeline")
# Placeholder values the model sometimes emits for "not learned yet" — ignore.
_PLACEHOLDER_VALUES = {"not specified", "unknown", "none", "n/a", "na", "null", "tbd"}


@app.get("/health")
def health() -> dict:
    """Read-only liveness probe (used to keep the host awake)."""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    From: str = Form(default=""),
    Body: str = Form(default=""),
    ProfileName: str = Form(default=""),
) -> Response:
    """Twilio posts inbound WhatsApp messages here (form-encoded)."""
    await request.form()  # ensures Twilio's payload is fully parsed/logged below
    log.info("Inbound from %s: %r", From, Body)

    phone = normalize_phone(From)
    reply = run_conversation_turn(phone, Body, ProfileName, source="whatsapp-inbound")

    twiml = MessagingResponse()
    msg = twiml.message(reply["reply_text"])
    for url in reply.get("send_media_urls", []):
        resolved = resolve_media_url(url)
        if resolved:
            msg.media(resolved)
    return Response(content=str(twiml), media_type="application/xml")


def run_conversation_turn(phone: str, body: str, name: str, source: str) -> dict:
    """Core agent turn, shared by the Twilio webhook and the web demo.

    Returns {reply_text, send_media_urls}. `source` and `name` are only used
    if this phone/session doesn't have a lead row yet.
    """
    lead = sheets.get_lead(phone)
    if lead is None:
        lead = sheets.upsert_lead(
            {
                "phone": phone,
                "name": name or "",
                "source": source,
                "status": "contacted",
            }
        )

    try:
        action = agent.run_agent(lead, body)
    except Exception as e:  # noqa: BLE001 - never leave the lead without a reply
        log.exception("Agent failed for %s: %s", phone, e)
        return {
            "reply_text": "Sorry, I'm having a brief issue — could you send that again?",
            "send_media_urls": [],
            "quick_replies": [],
        }

    fields = {"last_message": body}
    extracted = action.get("extracted") or {}
    for key in _EXTRACT_FIELDS:
        val = str(extracted.get(key, "") or "").strip()
        if val and val.lower() not in _PLACEHOLDER_VALUES:
            fields[key] = val
    if action.get("status"):
        fields["status"] = action["status"]
    if action.get("score") and str(action["score"]).lower() != "null":
        fields["score"] = action["score"]
    if action.get("stage"):
        fields["stage"] = action["stage"]
    fields["history_json"] = json.dumps(action.get("_history", []), ensure_ascii=False)

    sheets.update_lead_fields(phone, fields)

    return {
        "reply_text": action.get("reply_text", "Thanks! How can I help?"),
        "send_media_urls": action.get("send_media_urls", []),
        "quick_replies": action.get("quick_replies", []),
    }


# --- Web chat demo: same agent + sheet, no WhatsApp needed ------------------


class DemoStartIn(BaseModel):
    session_id: str
    name: str


class DemoChatIn(BaseModel):
    session_id: str
    name: str = ""
    message: str


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    return pages.render_demo_chat_page()


@app.post("/demo/start")
def demo_start(payload: DemoStartIn) -> dict:
    """Create the demo lead row and return the (static) opener text."""
    phone = web_session_phone(payload.session_id)
    name = payload.name.strip() or "there"
    sheets.upsert_lead(
        {"phone": phone, "name": name, "source": "web-demo", "status": "contacted"}
    )
    opener = OPENER_TEMPLATE.format(name=name, builder=config.BUILDER_NAME)
    return {"reply_text": opener, "quick_replies": ["YES"]}


@app.post("/demo/chat")
def demo_chat(payload: DemoChatIn) -> dict:
    phone = web_session_phone(payload.session_id)
    reply = run_conversation_turn(phone, payload.message, payload.name, source="web-demo")
    media = [resolve_media_url(u) for u in reply.get("send_media_urls", [])]
    return {
        "reply_text": reply["reply_text"],
        "media_urls": [u for u in media if u],
        "quick_replies": reply.get("quick_replies", []),
    }


@app.get("/demo/history")
def demo_history(session_id: str) -> dict:
    """Let the browser rebuild the transcript after a page refresh."""
    phone = web_session_phone(session_id)
    lead = sheets.get_lead(phone)
    if not lead:
        return {"exists": False, "history": []}
    history = []
    if lead.get("history_json"):
        try:
            history = json.loads(lead["history_json"])
        except (json.JSONDecodeError, TypeError):
            history = []
    return {"exists": True, "name": lead.get("name", ""), "history": history}


# --- Admin panel: leads dashboard + property inventory ----------------------

_security = HTTPBasic()
_ALLOWED_MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def _require_admin(creds: HTTPBasicCredentials = Depends(_security)) -> str:
    """HTTP Basic auth against ADMIN_USER / ADMIN_PASSWORD."""
    ok_user = secrets.compare_digest(creds.username, config.ADMIN_USER)
    ok_pass = secrets.compare_digest(creds.password, config.ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


@app.get("/admin/leads", response_class=HTMLResponse)
def admin_leads(_: str = Depends(_require_admin)) -> str:
    return pages.render_leads_page(sheets.get_all_leads())


@app.get("/admin/properties", response_class=HTMLResponse)
def admin_properties(_: str = Depends(_require_admin)) -> str:
    return pages.render_properties_page(sheets.get_properties(only_available=False))


@app.post("/admin/properties")
async def admin_add_property(
    _: str = Depends(_require_admin),
    title: str = Form(...),
    type: str = Form(default=""),
    location: str = Form(default=""),
    price: str = Form(default=""),
    available: str = Form(default="yes"),
    photos: list[UploadFile] = File(default=[]),
) -> Response:
    media_urls: list[str] = []
    for photo in photos:
        if not photo or not photo.filename:
            continue
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in _ALLOWED_MEDIA_EXT:
            rows = sheets.get_properties(only_available=False)
            page = pages.render_properties_page(
                rows,
                f"⚠️ Unsupported file type '{ext}' ({photo.filename}). "
                "Use jpg/png/webp for photos or mp4/mov/webm for video.",
            )
            return HTMLResponse(page, status_code=400)
        fname = f"{int(time.time())}_{secrets.token_hex(3)}{ext}"
        with open(os.path.join(_MEDIA_DIR, fname), "wb") as f:
            f.write(await photo.read())
        media_urls.append(f"media/{fname}")  # relative; resolved to absolute at send time

    sheets.add_property(
        {
            "title": title,
            "type": type,
            "location": location,
            "price": price,
            "media_urls": media_urls,
            "available": available,
        }
    )
    return RedirectResponse(
        url="/admin/properties", status_code=status.HTTP_303_SEE_OTHER
    )
