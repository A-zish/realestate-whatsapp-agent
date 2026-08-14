"""FastAPI app — multi-tenant real estate lead agent (Phase S1/S2 SaaS).

Any number of agencies ("accounts") can sign up. Each gets their own login,
their own branded AI agent, their own leads/properties (Postgres via
Supabase, strictly account_id-scoped everywhere — see app/db.py), and their
own shareable web-chat link at /demo/<slug>.

Entry points:
  - /signup, /login, /logout        real accounts (Supabase Auth + our own
                                     session cookie — see app/auth.py)
  - /dashboard, /dashboard/*        the logged-in agency's leads/properties/
                                     settings (session-auth protected)
  - /demo/<slug>                    a shareable, WhatsApp-styled browser
                                     chat for one specific account — no
                                     WhatsApp/Twilio sandbox needed
  - /webhook                        Twilio's inbound WhatsApp webhook;
                                     resolves which account owns the number
                                     that was messaged

Inbound flow for either channel (see run_conversation_turn):
  1. Look up the lead by (account, phone); create the row if unknown.
  2. Run the AI agent over that account's branding + conversation history.
  3. Reply (TwiML for Twilio, JSON for the web demo), including any property
     media the agent chose to send.
  4. Persist extracted fields, score, status, stage, and history back to
     Postgres, scoped to that account.
"""
import logging
import os

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
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse

from app import agent, auth, db, pages, storage
from app.auth import NotAuthenticated
from app.messages import OPENER_TEMPLATE
from app.utils import normalize_phone, resolve_media_url, web_session_phone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("realestate")

app = FastAPI(title="Real Estate Lead Agent (Multi-tenant)")

_ALLOWED_MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}

# Fields the agent extracts -> lead columns. Only non-empty values overwrite.
_EXTRACT_FIELDS = ("intent", "location_pref", "property_type", "budget", "timeline")
# Placeholder values the model sometimes emits for "not learned yet" — ignore.
_PLACEHOLDER_VALUES = {"not specified", "unknown", "none", "n/a", "na", "null", "tbd"}


@app.exception_handler(NotAuthenticated)
def _redirect_to_login(request: Request, exc: NotAuthenticated) -> Response:
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/health")
def health() -> dict:
    """Read-only liveness probe (used to keep the host awake)."""
    return {"status": "ok"}


# --- Core conversation engine, shared by Twilio + every account's web demo --


def run_conversation_turn(account: dict, phone: str, body: str, name: str, source: str) -> dict:
    """One agent turn for one account's lead. Returns {reply_text, send_media_urls, quick_replies}."""
    account_id = account["id"]
    lead = db.get_lead(account_id, phone)
    if lead is None:
        lead = db.upsert_lead(
            account_id, {"phone": phone, "name": name or "", "source": source, "status": "contacted"}
        )

    try:
        action = agent.run_agent(account, lead, body)
    except Exception as e:  # noqa: BLE001 - never leave the lead without a reply
        log.exception("Agent failed for %s (account=%s): %s", phone, account.get("slug"), e)
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
    fields["history_json"] = action.get("_history", [])  # JSONB column: store the list directly

    db.update_lead_fields(account_id, phone, fields)

    return {
        "reply_text": action.get("reply_text", "Thanks! How can I help?"),
        "send_media_urls": action.get("send_media_urls", []),
        "quick_replies": action.get("quick_replies", []),
    }


# --- Twilio WhatsApp webhook (single shared number for now — see S4) --------


@app.post("/webhook")
async def webhook(
    request: Request,
    From: str = Form(default=""),
    To: str = Form(default=""),
    Body: str = Form(default=""),
    ProfileName: str = Form(default=""),
) -> Response:
    """Twilio posts inbound WhatsApp messages here (form-encoded)."""
    await request.form()  # ensures Twilio's payload is fully parsed/logged below
    log.info("Inbound from %s to %s: %r", From, To, Body)

    account = db.get_account_by_twilio_number(To)
    twiml = MessagingResponse()
    if account is None:
        log.error("No account configured for WhatsApp number %s", To)
        twiml.message("Sorry, this number isn't set up yet.")
        return Response(content=str(twiml), media_type="application/xml")

    phone = normalize_phone(From)
    reply = run_conversation_turn(account, phone, Body, ProfileName, source="whatsapp-inbound")

    msg = twiml.message(reply["reply_text"])
    for url in reply.get("send_media_urls", []):
        resolved = resolve_media_url(url)
        if resolved:
            msg.media(resolved)
    return Response(content=str(twiml), media_type="application/xml")


# --- Accounts: signup / login / logout --------------------------------------


def _set_session_cookie(response: Response, user_id: str, account_id: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE_NAME,
        auth.make_session_cookie_value(user_id, account_id),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


@app.get("/signup", response_class=HTMLResponse)
def signup_page() -> str:
    return pages.render_signup_page()


@app.post("/signup")
async def signup_submit(
    agency_name: str = Form(...), email: str = Form(...), password: str = Form(...)
) -> Response:
    try:
        user_id = auth.sign_up(email, password)
    except Exception as e:  # noqa: BLE001 - show the signup form again with the error
        return HTMLResponse(pages.render_signup_page(error=str(e)), status_code=400)

    account = db.create_account(agency_name=agency_name)
    db.link_user_to_account(user_id, account["id"])

    resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(resp, user_id, account["id"])
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return pages.render_login_page()


@app.post("/login")
async def login_submit(email: str = Form(...), password: str = Form(...)) -> Response:
    try:
        user_id = auth.sign_in(email, password)
    except Exception:  # noqa: BLE001 - never leak Supabase's raw error to the form
        return HTMLResponse(pages.render_login_page(error="Invalid email or password."), status_code=401)

    account_id = db.get_account_id_for_user(user_id)
    if account_id is None:
        return HTMLResponse(
            pages.render_login_page(error="No agency account is linked to this login."),
            status_code=400,
        )

    resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(resp, user_id, account_id)
    return resp


@app.post("/logout")
def logout() -> Response:
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(auth.SESSION_COOKIE_NAME)
    return resp


# --- Dashboard: leads / properties / settings (session-auth protected) ------


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(account: dict = Depends(auth.get_current_account)) -> str:
    return pages.render_leads_page(db.get_all_leads(account["id"]), account)


@app.get("/dashboard/properties", response_class=HTMLResponse)
def dashboard_properties(account: dict = Depends(auth.get_current_account)) -> str:
    return pages.render_properties_page(db.get_properties(account["id"], only_available=False), account)


@app.post("/dashboard/properties")
async def dashboard_add_property(
    account: dict = Depends(auth.get_current_account),
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
            rows = db.get_properties(account["id"], only_available=False)
            page = pages.render_properties_page(
                rows,
                account,
                message=f"⚠️ Unsupported file type '{ext}' ({photo.filename}). "
                "Use jpg/png/webp for photos or mp4/mov/webm for video.",
            )
            return HTMLResponse(page, status_code=400)
        content = await photo.read()
        url = storage.upload_media(
            account["slug"], photo.filename, content, photo.content_type or "application/octet-stream"
        )
        media_urls.append(url)

    db.add_property(
        account["id"],
        {"title": title, "type": type, "location": location, "price": price,
         "media_urls": media_urls, "available": available},
    )
    return RedirectResponse(url="/dashboard/properties", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard/settings", response_class=HTMLResponse)
def dashboard_settings(account: dict = Depends(auth.get_current_account)) -> str:
    return pages.render_settings_page(account)


@app.post("/dashboard/settings")
async def dashboard_settings_submit(
    account: dict = Depends(auth.get_current_account),
    agency_name: str = Form(...),
    agent_name: str = Form(...),
    city: str = Form(...),
    custom_instructions: str = Form(default=""),
) -> Response:
    db.update_account(
        account["id"],
        {"agency_name": agency_name, "agent_name": agent_name, "city": city,
         "custom_instructions": custom_instructions},
    )
    return RedirectResponse(url="/dashboard/settings", status_code=status.HTTP_303_SEE_OTHER)


# --- Web chat demo: one shareable link per account, no WhatsApp needed ------


class DemoStartIn(BaseModel):
    session_id: str
    name: str


class DemoChatIn(BaseModel):
    session_id: str
    name: str = ""
    message: str


def _get_account_or_404(slug: str) -> dict:
    account = db.get_account_by_slug(slug)
    if account is None:
        raise HTTPException(status_code=404, detail="No such agency demo link")
    return account


@app.get("/demo/{slug}", response_class=HTMLResponse)
def demo_page(slug: str) -> str:
    return pages.render_demo_chat_page(_get_account_or_404(slug))


@app.post("/demo/{slug}/start")
def demo_start(slug: str, payload: DemoStartIn) -> dict:
    account = _get_account_or_404(slug)
    phone = web_session_phone(payload.session_id)
    name = payload.name.strip() or "there"
    db.upsert_lead(
        account["id"], {"phone": phone, "name": name, "source": "web-demo", "status": "contacted"}
    )
    opener = OPENER_TEMPLATE.format(name=name, builder=account["agency_name"])
    return {"reply_text": opener, "quick_replies": ["YES"]}


@app.post("/demo/{slug}/chat")
def demo_chat(slug: str, payload: DemoChatIn) -> dict:
    account = _get_account_or_404(slug)
    phone = web_session_phone(payload.session_id)
    reply = run_conversation_turn(account, phone, payload.message, payload.name, source="web-demo")
    media = [resolve_media_url(u) for u in reply.get("send_media_urls", [])]
    return {
        "reply_text": reply["reply_text"],
        "media_urls": [u for u in media if u],
        "quick_replies": reply.get("quick_replies", []),
    }


@app.get("/demo/{slug}/history")
def demo_history(slug: str, session_id: str) -> dict:
    """Let the browser rebuild the transcript after a page refresh."""
    account = _get_account_or_404(slug)
    phone = web_session_phone(session_id)
    lead = db.get_lead(account["id"], phone)
    if not lead:
        return {"exists": False, "history": []}
    return {"exists": True, "name": lead.get("name", ""), "history": lead.get("history_json") or []}
