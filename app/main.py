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
import csv
import io
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse

from app import agent, auth, config, db, importer, pages, ratelimit, storage, twilio_client
from app.auth import NotAuthenticated
from app.messages import OPENER_TEMPLATE
from app.twilio_verify import verify_twilio_signature
from app.utils import normalize_phone, resolve_media_url, web_session_phone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("realestate")

app = FastAPI(title="LeadPilot by Ramatech")


@app.on_event("startup")
def _startup() -> None:
    config.assert_secure_session_secret()

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_APP_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(_APP_DIR, "templates"))

_ALLOWED_MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}

# Offered in the property form; broader than whatever is currently in stock so
# an agency can list anything they actually sell.
_PROPERTY_TYPES = [
    "1BHK", "2BHK", "3BHK", "4BHK+", "Studio", "Villa", "Plot/Land", "Farmhouse",
    "Shop", "Showroom", "Office Space", "Commercial Space", "Warehouse/Godown",
    "Industrial Shed", "PG/Hostel", "Other",
]

_SAMPLE_PROMPTS = [
    "Looking for a 3BHK in Jaipur",
    "What's your budget range?",
    "Show me photos",
    "Why should I buy this?",
    "It's too expensive for me",
    "I want to book a site visit",
]


def _lead_link(request: Request, account: dict) -> str:
    """The public, shareable capture link for this account."""
    base = (config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
    return f"{base}/demo/{account['slug']}"


def _render(request: Request, template: str, account: dict, **ctx) -> HTMLResponse:
    """Render a dashboard page with the context every page's shell needs."""
    props = db.get_properties(account["id"], only_available=False)
    base_ctx = {
        "account": account,
        "lead_link": _lead_link(request, account),
        "onboarding_done": bool(account.get("onboarding_completed_at")),
        "property_count": len(props),
    }
    return templates.TemplateResponse(request, template, {**base_ctx, **ctx})


def _client_ip(request: Request) -> str:
    return ratelimit.client_ip(request.headers, request.client.host if request.client else None)


def _require_onboarding(account: dict) -> Response | None:
    if account.get("onboarding_completed_at"):
        return None
    return RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)


def _apply_lead_filters(
    leads: list[dict],
    *,
    q: str = "",
    score: str = "",
    status_filter: str = "",
    view: str = "call",
) -> list[dict]:
    if q:
        needle = q.lower()
        leads = [
            lead for lead in leads
            if needle in " ".join(
                str(lead.get(f, "")) for f in
                ("name", "phone", "location_pref", "property_type", "budget",
                 "last_message", "score_reason", "campaign")
            ).lower()
        ]
    if score:
        leads = [lead for lead in leads if (lead.get("score") or "").upper() == score.upper()]
    if status_filter:
        leads = [lead for lead in leads if lead.get("status") == status_filter]
    view = (view or "call").lower()
    if view == "call" and not score:
        leads = [
            lead for lead in leads
            if (lead.get("qualification_status") or "") == "scored"
            and (lead.get("score") or "").upper() in {"HOT", "WARM"}
        ]
    elif view == "cold" and not score:
        leads = [
            lead for lead in leads
            if (lead.get("qualification_status") or "") == "scored"
            and (lead.get("score") or "").upper() == "COLD"
        ]
    elif view == "pending":
        leads = [lead for lead in leads if (lead.get("qualification_status") or "") == "pending"]
    return leads


def _ingest_lead(account_id, entry: dict, *, default_source: str) -> tuple[str, dict]:
    """Upsert a form/CSV/webhook lead as pending. Returns ('created'|'updated', lead)."""
    phone = normalize_phone(entry.get("phone", ""))
    if not phone:
        raise ValueError("phone is required")
    existing = db.get_lead(account_id, phone)
    source = (entry.get("source") or default_source or "").strip() or default_source
    payload = {
        "phone": phone,
        "name": entry.get("name") or (existing or {}).get("name") or "",
        "source": source,
        "campaign": entry.get("campaign") or "",
        "gclid": entry.get("gclid") or "",
    }
    if not existing:
        payload["status"] = "new"
        payload["qualification_status"] = "pending"
    elif (existing.get("qualification_status") or "") == "pending":
        payload["qualification_status"] = "pending"
    db.upsert_lead(account_id, payload)
    return ("updated" if existing else "created"), db.get_lead(account_id, phone) or {}

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
            account_id,
            {
                "phone": phone,
                "name": name or "",
                "source": source,
                "status": "contacted",
                "qualification_status": "in_conversation",
            },
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
        fields["qualification_status"] = "scored"
    else:
        fields["qualification_status"] = "in_conversation"
    reason = str(action.get("score_reason") or "").strip()
    if reason:
        fields["score_reason"] = reason
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
async def webhook(request: Request) -> Response:
    """Twilio posts inbound WhatsApp messages here (form-encoded)."""
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if not verify_twilio_signature(request, params):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    From = params.get("From", "")
    To = params.get("To", "")
    Body = params.get("Body", "")
    ProfileName = params.get("ProfileName", "")
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
        secure=config.cookie_secure(),
    )


def _auth_page(request: Request, mode: str, error: str = "", code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "auth.html", {"mode": mode, "error": error}, status_code=code
    )


@app.get("/")
def root() -> Response:
    return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return _auth_page(request, "signup")


@app.post("/signup")
async def signup_submit(
    request: Request,
    agency_name: str = Form(...), email: str = Form(...), password: str = Form(...)
) -> Response:
    if not ratelimit.limiter.allow(f"signup:{_client_ip(request)}", limit=5, window_s=900):
        return _auth_page(request, "signup", "Too many signup attempts. Try again later.", 429)
    # Validate the login BEFORE creating the account, so a rejected signup
    # (duplicate email, weak password) doesn't leave an orphaned account.
    email_norm = auth.normalize_email(email)
    if db.get_user_by_email(email_norm) is not None:
        return _auth_page(request, "signup", "That email is already registered.", 400)
    if len(password) < 6:
        return _auth_page(request, "signup", "Password must be at least 6 characters.", 400)

    account = db.create_account(agency_name=agency_name)
    try:
        user_id = auth.sign_up(email_norm, password, account["id"])
    except auth.AuthError as e:
        return _auth_page(request, "signup", str(e), 400)

    resp = RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(resp, user_id, account["id"])
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _auth_page(request, "login")


@app.post("/login")
async def login_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> Response:
    try:
        user_id = auth.sign_in(email, password)
    except auth.AuthError:
        return _auth_page(request, "login", "Invalid email or password.", 401)

    account_id = db.get_account_id_for_user(user_id)
    if account_id is None:
        return _auth_page(request, "login", "No agency account is linked to this login.", 400)

    dest = "/dashboard"
    logged_account = db.get_account_by_id(account_id)
    if logged_account and not logged_account.get("onboarding_completed_at"):
        dest = "/onboarding"
    resp = RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(resp, user_id, account_id)
    return resp


@app.post("/logout")
def logout() -> Response:
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(auth.SESSION_COOKIE_NAME)
    return resp


# --- Dashboard (session-auth protected) -------------------------------------


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, account: dict = Depends(auth.get_current_account)):
    gate = _require_onboarding(account)
    if gate:
        return gate
    stats = db.get_lead_stats(account["id"])
    return _render(request, "overview.html", account,
                   active="overview", stats=stats, lead_count=stats["total"])


@app.get("/dashboard/leads", response_class=HTMLResponse)
def dashboard_leads(
    request: Request,
    q: str = "",
    score: str = "",
    status_filter: str = "",
    view: str = "call",
    account: dict = Depends(auth.get_current_account),
):
    gate = _require_onboarding(account)
    if gate:
        return gate
    leads = db.get_all_leads(account["id"])
    stats = db.get_lead_stats(account["id"])
    all_statuses = sorted(stats["statuses"].keys())
    filtered = _apply_lead_filters(
        leads, q=q, score=score, status_filter=status_filter, view=view
    )
    return _render(
        request, "leads.html", account,
        active="leads", leads=list(reversed(filtered)), stats=stats,
        lead_count=stats["total"], q=q, score_filter=score,
        status_filter=status_filter, all_statuses=all_statuses, view=view,
    )


@app.get("/dashboard/leads.csv")
def dashboard_leads_csv(
    request: Request,
    q: str = "",
    score: str = "",
    status_filter: str = "",
    view: str = "call",
    account: dict = Depends(auth.get_current_account),
):
    gate = _require_onboarding(account)
    if gate:
        return gate
    leads = _apply_lead_filters(
        db.get_all_leads(account["id"]),
        q=q, score=score, status_filter=status_filter, view=view,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "name", "phone", "score", "score_reason", "status", "qualification_status",
        "budget", "location", "timeline", "property_type", "source", "campaign",
        "gclid", "updated_at",
    ])
    for lead in reversed(leads):
        writer.writerow([
            lead.get("name", ""), lead.get("phone", ""), lead.get("score", ""),
            lead.get("score_reason", ""), lead.get("status", ""),
            lead.get("qualification_status", ""), lead.get("budget", ""),
            lead.get("location_pref", ""), lead.get("timeline", ""),
            lead.get("property_type", ""), lead.get("source", ""),
            lead.get("campaign", ""), lead.get("gclid", ""), lead.get("updated_at", ""),
        ])
    buf.seek(0)
    filename = f"leads-{view}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/dashboard/leads/{lead_id}", response_class=HTMLResponse)
def dashboard_lead_detail(
    request: Request, lead_id: UUID, account: dict = Depends(auth.get_current_account)
):
    gate = _require_onboarding(account)
    if gate:
        return gate
    lead = db.get_lead_by_id(account["id"], lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _render(request, "lead_detail.html", account, active="leads", lead=lead)


@app.post("/dashboard/leads/{lead_id}/status")
def dashboard_lead_status(
    lead_id: UUID,
    status_value: str = Form(..., alias="status"),
    account: dict = Depends(auth.get_current_account),
):
    lead = db.get_lead_by_id(account["id"], lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    allowed = {"contacted", "visit_booked", "qualified", "dead"}
    if status_value not in allowed:
        raise HTTPException(status_code=400, detail="Unknown status")
    db.update_lead_fields(account["id"], lead["phone"], {"status": status_value})
    return RedirectResponse(
        url=f"/dashboard/leads/{lead_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/dashboard/leads/{lead_id}/delete")
def dashboard_lead_delete(
    lead_id: UUID, account: dict = Depends(auth.get_current_account)
) -> Response:
    if not db.delete_lead(account["id"], lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return RedirectResponse(url="/dashboard/leads?view=all", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/dashboard/leads/bulk-delete")
async def dashboard_leads_bulk_delete(
    request: Request, account: dict = Depends(auth.get_current_account)
) -> Response:
    form = await request.form()
    scope = str(form.get("scope") or "selected")
    view = str(form.get("view") or "all")
    if scope == "pending":
        db.delete_pending_leads(account["id"])
        dest = "/dashboard/leads?view=pending"
    else:
        ids = [str(v) for v in form.getlist("lead_ids")]
        db.delete_leads(account["id"], ids)
        dest = f"/dashboard/leads?view={view}" if view in {"call", "cold", "pending", "all"} else "/dashboard/leads?view=all"
    return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard/properties", response_class=HTMLResponse)
def dashboard_properties(request: Request, account: dict = Depends(auth.get_current_account)):
    return _render(request, "properties.html", account,
                   active="properties",
                   rows=db.get_properties(account["id"], only_available=False),
                   property_types=_PROPERTY_TYPES, message="")


@app.post("/dashboard/properties")
async def dashboard_add_property(
    request: Request,
    account: dict = Depends(auth.get_current_account),
    title: str = Form(...),
    type: str = Form(default=""),
    location: str = Form(default=""),
    price: str = Form(default=""),
    available: str = Form(default="yes"),
    photos: list[UploadFile] = File(default=[]),
    nxt: str = Form(default=""),
) -> Response:
    media_urls: list[str] = []
    for photo in photos:
        if not photo or not photo.filename:
            continue
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in _ALLOWED_MEDIA_EXT:
            return _render(
                request, "properties.html", account,
                active="properties",
                rows=db.get_properties(account["id"], only_available=False),
                property_types=_PROPERTY_TYPES,
                message=f"Unsupported file type '{ext}' ({photo.filename}). "
                        "Use jpg/png/webp for photos or mp4/mov/webm for video.",
            )
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
    dest = (nxt or request.query_params.get("next") or "").strip()
    if dest.startswith("/onboarding"):
        return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/dashboard/properties", status_code=status.HTTP_303_SEE_OTHER)


# --- Playground: test the agent without creating real leads -----------------


class PlaygroundIn(BaseModel):
    message: str
    history: list[dict] = []


@app.get("/dashboard/playground", response_class=HTMLResponse)
def dashboard_playground(request: Request, account: dict = Depends(auth.get_current_account)):
    return _render(request, "playground.html", account,
                   active="playground", sample_prompts=_SAMPLE_PROMPTS)


@app.post("/dashboard/playground/chat")
def playground_chat(payload: PlaygroundIn, account: dict = Depends(auth.get_current_account)) -> dict:
    """Run one agent turn against a throwaway, client-held conversation.

    Deliberately never touches the leads table — the whole point of the
    playground is that an agency can stress-test their agent without
    polluting real lead data or their dashboard numbers.
    """
    fake_lead = {"phone": "playground", "name": "Test", "history_json": payload.history}
    try:
        action = agent.run_agent(account, fake_lead, payload.message)
    except Exception as e:  # noqa: BLE001 - surface a usable message in the UI
        log.exception("Playground agent failed for %s: %s", account.get("slug"), e)
        return {"reply_text": "The agent hit an error — try again.",
                "media_urls": [], "quick_replies": [], "history": payload.history}

    media = [resolve_media_url(u) for u in action.get("send_media_urls", [])]
    return {
        "reply_text": action.get("reply_text", ""),
        "media_urls": [u for u in media if u],
        "quick_replies": action.get("quick_replies", []),
        "history": action.get("_history", []),
    }


@app.get("/dashboard/settings", response_class=HTMLResponse)
def dashboard_settings(
    request: Request,
    saved: int = 0,
    token: str = "",
    account: dict = Depends(auth.get_current_account),
):
    ingest_url = ""
    if account.get("has_ingest_token") or token:
        base = (config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
        ingest_url = f"{base}/api/v1/leads"
    return _render(
        request, "settings.html", account, active="settings",
        saved=bool(saved), ingest_token=token, ingest_url=ingest_url,
    )


@app.post("/dashboard/settings")
async def dashboard_settings_submit(
    account: dict = Depends(auth.get_current_account),
    agency_name: str = Form(...),
    agent_name: str = Form(...),
    city: str = Form(default=""),
    custom_instructions: str = Form(default=""),
) -> Response:
    db.update_account(
        account["id"],
        {"agency_name": agency_name, "agent_name": agent_name, "city": city,
         "custom_instructions": custom_instructions},
    )
    return RedirectResponse(url="/dashboard/settings?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/dashboard/settings/ingest-token")
def dashboard_rotate_ingest_token(account: dict = Depends(auth.get_current_account)) -> Response:
    token = db.rotate_ingest_token(account["id"])
    return RedirectResponse(
        url=f"/dashboard/settings?token={token}", status_code=status.HTTP_303_SEE_OTHER
    )


# --- Import leads from a spreadsheet ----------------------------------------


@app.get("/dashboard/import", response_class=HTMLResponse)
def dashboard_import(request: Request, account: dict = Depends(auth.get_current_account)):
    return _render(request, "import.html", account, active="import",
                   result=None, error="", parsed=None)


@app.post("/dashboard/import", response_class=HTMLResponse)
async def dashboard_import_preview(
    request: Request,
    account: dict = Depends(auth.get_current_account),
    file: UploadFile = File(...),
):
    """Parse the upload and show a preview — nothing is saved at this step."""
    try:
        parsed = importer.parse_leads(file.filename or "", await file.read())
    except Exception as e:  # noqa: BLE001 - show the reason on the page
        log.warning("Import parse failed for %s: %s", account.get("slug"), e)
        return _render(request, "import.html", account, active="import",
                       result=None, error=str(e), parsed=None)

    return _render(request, "import.html", account, active="import",
                   result=None, error="", parsed=parsed, filename=file.filename)


class ImportConfirmIn(BaseModel):
    leads: list[dict]
    source: str = "google-ads"


@app.post("/dashboard/import/confirm")
def dashboard_import_confirm(
    payload: ImportConfirmIn, account: dict = Depends(auth.get_current_account)
) -> dict:
    """Write previewed leads as pending — callers do not see them until scored."""
    default_source = payload.source.strip() or "google-ads"
    created = updated = 0
    for entry in payload.leads:
        try:
            kind, _ = _ingest_lead(
                account["id"],
                {**entry, "source": entry.get("source") or default_source},
                default_source=default_source,
            )
        except ValueError:
            continue
        if kind == "created":
            created += 1
        else:
            updated += 1

    log.info("Imported leads for %s: %d new, %d updated", account.get("slug"), created, updated)
    return {"created": created, "updated": updated, "whatsapp_connected": account.get("whatsapp_status") == "connected"}


# --- Sending WhatsApp openers ------------------------------------------------


class SendOpenersIn(BaseModel):
    phones: list[str] = []       # empty = every pending lead


@app.post("/dashboard/send-openers")
def dashboard_send_openers(
    payload: SendOpenersIn, account: dict = Depends(auth.get_current_account)
) -> dict:
    """Send the opening WhatsApp message — only if this tenant connected WhatsApp."""
    block = db.whatsapp_send_preflight(account)
    if block:
        raise HTTPException(status_code=400, detail=block)
    leads = db.get_all_leads(account["id"])
    if payload.phones:
        wanted = {normalize_phone(p) for p in payload.phones}
        targets = [l for l in leads if l["phone"] in wanted]
    else:
        targets = [l for l in leads if (l.get("qualification_status") or "") == "pending"]
    if len(targets) > 10:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Refusing to WhatsApp {len(targets)} leads at once (sandbox daily limit). "
                "Delete dummy CSV rows first, or send to at most 10 numbers."
            ),
        )

    results = []
    for lead in targets:
        name = lead.get("name") or "there"
        body = OPENER_TEMPLATE.format(name=name, builder=account["agency_name"])
        try:
            sid = twilio_client.send_whatsapp(
                account,
                lead["phone"],
                body,
                own_only=True,
                content_variables={"1": name, "2": account.get("agency_name") or "us"},
            )
            db.record_whatsapp_attempt(account["id"], lead["phone"], sid=sid, error="")
            db.update_lead_fields(
                account["id"],
                lead["phone"],
                {"status": "contacted", "qualification_status": "in_conversation"},
            )
            results.append({"phone": lead["phone"], "name": name, "ok": True, "error": "", "sid": sid})
        except Exception as e:  # noqa: BLE001 - one bad number must not stop the run
            err = twilio_client.friendly_error(e)
            log.warning("Opener failed for %s: %s", lead["phone"], e)
            db.record_whatsapp_attempt(account["id"], lead["phone"], sid="", error=err)
            results.append({"phone": lead["phone"], "name": name, "ok": False,
                            "error": err, "sid": ""})

    sent = sum(1 for r in results if r["ok"])
    return {"sent": sent, "failed": len(results) - sent, "results": results}


# --- Connect WhatsApp (per agency) ------------------------------------------


def _whatsapp_page_extras(request: Request, account: dict) -> dict:
    from app import crypto

    return {
        "preflight": db.whatsapp_send_preflight(account),
        "checklist": {
            "encryption": crypto.encryption_ready(),
            "connected": account.get("whatsapp_status") == "connected",
            "has_creds": bool(account.get("has_own_twilio")),
            "has_from": bool((account.get("twilio_whatsapp_from") or "").strip()),
            "has_content_sid": bool((account.get("twilio_content_sid") or "").strip()),
            "public_https": bool(config.PUBLIC_BASE_URL.startswith("https://")),
            "webhook_url": (
                f"{config.PUBLIC_BASE_URL.rstrip('/')}/webhook" if config.PUBLIC_BASE_URL else ""
            ),
            "lead_link": _lead_link(request, account),
        },
    }


@app.get("/dashboard/whatsapp", response_class=HTMLResponse)
def dashboard_whatsapp(request: Request, saved: int = 0,
                       account: dict = Depends(auth.get_current_account)):
    from app import crypto

    error = ""
    if not crypto.encryption_ready():
        error = (
            "Twilio credentials cannot be saved until ENCRYPTION_KEY is set on the host. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return _render(
        request, "whatsapp.html", account, active="whatsapp",
        saved=bool(saved), error=error, test_result=None,
        **_whatsapp_page_extras(request, account),
    )


@app.post("/dashboard/whatsapp")
async def dashboard_whatsapp_save(
    request: Request,
    account: dict = Depends(auth.get_current_account),
    twilio_account_sid: str = Form(...),
    twilio_auth_token: str = Form(default=""),
    whatsapp_number: str = Form(...),
    twilio_content_sid: str = Form(default=""),
) -> Response:
    from app import crypto

    number = whatsapp_number.strip()
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{normalize_phone(number)}"
    try:
        db.set_whatsapp_credentials(
            account["id"], twilio_account_sid, twilio_auth_token, number,
            status="connected", content_sid=twilio_content_sid,
        )
    except ValueError as e:
        return _render(
            request, "whatsapp.html", account, active="whatsapp",
            saved=False, error=str(e), test_result=None,
            **_whatsapp_page_extras(request, account),
        )
    except crypto.EncryptionNotConfigured as e:
        return _render(
            request, "whatsapp.html", account, active="whatsapp",
            saved=False, error=str(e), test_result=None,
            **_whatsapp_page_extras(request, account),
        )
    except Exception as e:  # noqa: BLE001 - show a usable message instead of a 500
        log.exception("Saving WhatsApp credentials failed for %s: %s", account.get("slug"), e)
        return _render(
            request, "whatsapp.html", account, active="whatsapp",
            saved=False,
            error="Could not save the Twilio connection. Confirm ENCRYPTION_KEY is set "
                  "and Alembic migrations have run (whatsapp columns on accounts).",
            test_result=None,
            **_whatsapp_page_extras(request, account),
        )
    return RedirectResponse(url="/dashboard/whatsapp?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/dashboard/whatsapp/disconnect")
def dashboard_whatsapp_disconnect(account: dict = Depends(auth.get_current_account)) -> Response:
    db.clear_whatsapp_credentials(account["id"])
    return RedirectResponse(url="/dashboard/whatsapp", status_code=status.HTTP_303_SEE_OTHER)


class TestMessageIn(BaseModel):
    to: str


@app.post("/dashboard/whatsapp/test")
def dashboard_whatsapp_test(
    payload: TestMessageIn, account: dict = Depends(auth.get_current_account)
) -> dict:
    """Send a one-off test message so the agency can confirm the connection
    works before they run it against a real lead list."""
    block = db.whatsapp_send_preflight(account)
    if block:
        return {"ok": False, "sid": "", "error": block}
    body = (
        f"✅ WhatsApp is connected for {account['agency_name']}. "
        f"This is a test from your AI agent, {account.get('agent_name') or 'your assistant'}."
    )
    try:
        sid = twilio_client.send_whatsapp(
            account,
            payload.to,
            body,
            content_variables={
                "1": account.get("agent_name") or "Priya",
                "2": account.get("agency_name") or "us",
            },
        )
        phone = normalize_phone(payload.to)
        if phone:
            db.record_whatsapp_attempt(account["id"], phone, sid=sid, error="")
        return {"ok": True, "sid": sid, "error": ""}
    except Exception as e:  # noqa: BLE001 - report the reason in the UI
        err = twilio_client.friendly_error(e)
        log.warning("Test message failed for %s: %s", account.get("slug"), e)
        phone = normalize_phone(payload.to)
        if phone:
            db.record_whatsapp_attempt(account["id"], phone, sid="", error=err)
        return {"ok": False, "sid": "", "error": err}


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
def demo_start(request: Request, slug: str, payload: DemoStartIn) -> dict:
    if not ratelimit.limiter.allow(f"demo:{_client_ip(request)}:{slug}", limit=30, window_s=60):
        raise HTTPException(status_code=429, detail="Too many requests")
    account = _get_account_or_404(slug)
    phone = web_session_phone(payload.session_id)
    name = payload.name.strip() or "there"
    db.upsert_lead(
        account["id"],
        {
            "phone": phone,
            "name": name,
            "source": "web-demo",
            "status": "contacted",
            "qualification_status": "in_conversation",
        },
    )
    opener = OPENER_TEMPLATE.format(name=name, builder=account["agency_name"])
    return {"reply_text": opener, "quick_replies": ["YES"]}


@app.post("/demo/{slug}/chat")
def demo_chat(request: Request, slug: str, payload: DemoChatIn) -> dict:
    if not ratelimit.limiter.allow(f"demo:{_client_ip(request)}:{slug}", limit=30, window_s=60):
        raise HTTPException(status_code=429, detail="Too many requests")
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


# --- First-run onboarding ---------------------------------------------------


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(
    request: Request,
    step: int = 1,
    token: str = "",
    account: dict = Depends(auth.get_current_account),
):
    if account.get("onboarding_completed_at"):
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    step = min(max(step, 1), 4)
    ingest_url = ""
    base = (config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")).rstrip("/")
    if token:
        ingest_url = f"{base}/api/v1/leads"
    return _render(
        request, "onboarding.html", account,
        active="overview", step=step, ingest_token=token, ingest_url=ingest_url,
        property_types=_PROPERTY_TYPES,
    )


@app.post("/onboarding/profile")
async def onboarding_profile(
    account: dict = Depends(auth.get_current_account),
    agency_name: str = Form(...),
    agent_name: str = Form(...),
    city: str = Form(default=""),
) -> Response:
    db.update_account(
        account["id"],
        {"agency_name": agency_name, "agent_name": agent_name, "city": city},
    )
    return RedirectResponse(url="/onboarding?step=2", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/onboarding/ingest-token")
def onboarding_ingest_token(account: dict = Depends(auth.get_current_account)) -> Response:
    token = db.rotate_ingest_token(account["id"])
    return RedirectResponse(
        url=f"/onboarding?step=4&token={token}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/onboarding/complete")
def onboarding_complete(account: dict = Depends(auth.get_current_account)) -> Response:
    db.mark_onboarding_complete(account["id"])
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# --- Public ingest webhook (Zapier / landing form / Google Ads) -------------


class IngestLeadIn(BaseModel):
    phone: str
    name: str = ""
    source: str = "webhook"
    campaign: str = ""
    gclid: str = ""


@app.post("/api/v1/leads")
def api_ingest_lead(
    request: Request,
    payload: IngestLeadIn,
    authorization: str = Header(default=""),
) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer ingest token")
    if not ratelimit.limiter.allow(f"ingest:{token[:12]}", limit=60, window_s=60):
        raise HTTPException(status_code=429, detail="Too many ingest requests")
    account = db.get_account_by_ingest_token(token)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid ingest token")
    try:
        kind, lead = _ingest_lead(
            account["id"],
            payload.model_dump(),
            default_source="webhook",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "ok": True,
        "created": kind == "created",
        "phone": lead.get("phone"),
        "qualification_status": lead.get("qualification_status"),
    }

