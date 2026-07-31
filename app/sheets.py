"""Google Sheet access — the datastore AND dashboard (one row per lead).

State lives in the sheet (not a local DB) so it survives redeploys and is
human-readable. Auth is via a service account whose JSON key path comes from
the environment.

Public API:
    get_lead(phone)               -> dict | None
    upsert_lead(data: dict)       -> dict   (create or merge by phone)
    update_lead_fields(phone, {}) -> dict   (partial update of an existing row)
    get_properties(...)           -> list[dict], each with a "media" list
    add_property(dict incl. media_urls: list[str]) -> dict
"""
import json
import logging

import gspread
from google.oauth2.service_account import Credentials

from app import config
from app.utils import normalize_phone, now_iso

log = logging.getLogger(__name__)

# Column order for the `leads` tab. Order matters — it defines the sheet layout.
LEAD_COLUMNS = [
    "phone",          # E.164, PRIMARY KEY
    "name",
    "source",
    "status",         # new / contacted / qualifying / qualified / visit_booked / dead
    "score",          # HOT / WARM / COLD / ""
    "stage",          # location / type / budget / timeline / closing
    "intent",         # buy / rent / invest / unknown
    "location_pref",
    "property_type",
    "budget",
    "timeline",
    "last_message",
    "history_json",   # full conversation history as a JSON string
    "updated_at",     # ISO timestamp
]

WORKSHEET_NAME = "leads"

# The inventory the agent shows to leads (Phase v2 — builder-editable in Sheets).
PROPERTIES_TAB = "properties"
# media_urls holds a JSON array of one or more image/video URLs for the
# property (relative "media/x.png" uploads or absolute external URLs).
PROPERTY_COLUMNS = ["id", "title", "type", "location", "price", "media_urls", "available"]

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_spreadsheet = None
_worksheet: gspread.Worksheet | None = None
_properties_ws: gspread.Worksheet | None = None


def _load_credentials() -> Credentials:
    """Build service-account credentials from GOOGLE_SERVICE_ACCOUNT_JSON.

    Supports two forms so the same code works locally and on a host with no
    file uploads: a path to a JSON key file (local dev), or the JSON key
    content pasted directly into the env var (most PaaS hosts).
    """
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
    if raw.startswith("{"):
        return Credentials.from_service_account_info(json.loads(raw), scopes=_SCOPES)
    return Credentials.from_service_account_file(raw, scopes=_SCOPES)


def _get_spreadsheet():
    """Authorize once and open the spreadsheet (shared by all tabs)."""
    global _spreadsheet
    if _spreadsheet is None:
        config.require("GOOGLE_SHEET_ID")
        client = gspread.authorize(_load_credentials())
        _spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
    return _spreadsheet


def _get_or_create_ws(name: str, columns: list[str]) -> gspread.Worksheet:
    """Return a worksheet by name (creating it + its header row if missing)."""
    spreadsheet = _get_spreadsheet()
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=100, cols=len(columns))
        log.info("Created '%s' worksheet", name)
    _ensure_headers(ws, columns)
    return ws


def _get_worksheet() -> gspread.Worksheet:
    """The `leads` tab (datastore + dashboard)."""
    global _worksheet
    if _worksheet is None:
        _worksheet = _get_or_create_ws(WORKSHEET_NAME, LEAD_COLUMNS)
    return _worksheet


def _get_properties_ws() -> gspread.Worksheet:
    """The `properties` tab (builder-editable inventory)."""
    global _properties_ws
    if _properties_ws is None:
        _properties_ws = _get_or_create_ws(PROPERTIES_TAB, PROPERTY_COLUMNS)
    return _properties_ws


def _ensure_headers(ws: gspread.Worksheet, columns: list[str]) -> None:
    """Write the header row if it's missing or doesn't match the schema."""
    first_row = ws.row_values(1)
    if first_row[: len(columns)] != columns:
        ws.update(
            range_name=f"A1:{_col_letter(len(columns))}1",
            values=[columns],
        )
        log.info("Initialized header row for '%s'", ws.title)


def _col_letter(n: int) -> str:
    """1-based column index -> spreadsheet letter (1 -> A, 27 -> AA)."""
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _find_row_index(ws: gspread.Worksheet, phone: str) -> int | None:
    """Return the 1-based sheet row number for a phone, or None if absent."""
    phone_col = LEAD_COLUMNS.index("phone") + 1
    values = ws.col_values(phone_col)  # includes the header in position 0
    for i, val in enumerate(values[1:], start=2):  # data rows start at row 2
        if normalize_phone(val) == phone:
            return i
    return None


def _row_values(data: dict) -> list:
    """Project a lead dict onto the fixed column order (missing -> "")."""
    return [str(data.get(col, "") or "") for col in LEAD_COLUMNS]


def get_lead(phone: str) -> dict | None:
    """Fetch one lead by phone (normalized). Returns a dict or None."""
    phone = normalize_phone(phone)
    ws = _get_worksheet()
    row = _find_row_index(ws, phone)
    if row is None:
        return None
    values = ws.row_values(row)
    values += [""] * (len(LEAD_COLUMNS) - len(values))  # pad short rows
    return dict(zip(LEAD_COLUMNS, values))


def get_all_leads() -> list[dict]:
    """Return every lead row as a dict (in sheet order).

    `numericise_ignore=["all"]` keeps every value as a string — otherwise
    gspread parses "+919812345678" into an int and drops the leading '+'.
    """
    ws = _get_worksheet()
    records = ws.get_all_records(
        expected_headers=LEAD_COLUMNS, numericise_ignore=["all"]
    )
    return [{k: str(v) for k, v in rec.items()} for rec in records]


def upsert_lead(data: dict) -> dict:
    """Create a lead row, or merge fields into an existing one (key = phone)."""
    if not data.get("phone"):
        raise ValueError("upsert_lead requires a 'phone' field")

    phone = normalize_phone(data["phone"])
    data = {**data, "phone": phone, "updated_at": now_iso()}

    ws = _get_worksheet()
    row = _find_row_index(ws, phone)

    if row is None:
        ws.append_row(_row_values(data), value_input_option="RAW")
        log.info("Inserted lead %s", phone)
        return data

    existing = get_lead(phone) or {}
    merged = {**existing, **data}
    ws.update(
        range_name=f"A{row}:{_col_letter(len(LEAD_COLUMNS))}{row}",
        values=[_row_values(merged)],
        value_input_option="RAW",
    )
    log.info("Updated lead %s", phone)
    return merged


def update_lead_fields(phone: str, fields: dict) -> dict:
    """Partial update of specific columns for an existing lead.

    Convenience wrapper over upsert_lead that always stamps updated_at.
    """
    phone = normalize_phone(phone)
    return upsert_lead({**fields, "phone": phone})


# --- Properties (inventory) -------------------------------------------------

# Small TTL cache so we don't hit the Sheets API on every WhatsApp turn.
_props_cache: tuple[float, list[dict]] | None = None
_PROPS_TTL_SECONDS = 60


def _parse_media(raw: str) -> list[str]:
    """Parse the `media_urls` cell into a list of URLs.

    Stored as a JSON array (["url1","url2"]), but tolerant of a builder
    pasting a single plain URL directly into the sheet cell.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(u).strip() for u in parsed if str(u).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return [raw]  # legacy / manual single URL


def get_properties(only_available: bool = True, use_cache: bool = True) -> list[dict]:
    """Return inventory rows from the `properties` tab.

    Each row includes a "media" key: a list of image/video URLs (relative
    uploads or absolute external links) parsed from the media_urls cell.
    `only_available` drops rows whose `available` cell is no/false/0/sold.
    Cached for a minute to keep WhatsApp replies fast.
    """
    import time

    global _props_cache
    if use_cache and _props_cache and (time.time() - _props_cache[0]) < _PROPS_TTL_SECONDS:
        rows = _props_cache[1]
    else:
        ws = _get_properties_ws()
        records = ws.get_all_records(
            expected_headers=PROPERTY_COLUMNS, numericise_ignore=["all"]
        )
        rows = [{k: str(v).strip() for k, v in rec.items()} for rec in records]
        rows = [r for r in rows if r.get("id") or r.get("title")]  # skip blanks
        for r in rows:
            r["media"] = _parse_media(r.get("media_urls", ""))
        _props_cache = (time.time(), rows)

    if only_available:
        rows = [
            r
            for r in rows
            if str(r.get("available", "")).strip().lower()
            not in {"no", "false", "0", "sold"}
        ]
    return rows


def add_property(data: dict) -> dict:
    """Append a property row to the inventory tab. Auto-assigns id if missing.

    `data["media_urls"]` may be given as a list[str] (preferred) or an
    already-JSON-encoded string; either way it's stored as a JSON array.
    """
    global _props_cache
    ws = _get_properties_ws()
    if not data.get("id"):
        existing = ws.col_values(1)  # column A = id (incl. header)
        data["id"] = f"P-{len(existing):03d}"
    if not str(data.get("available", "")).strip():
        data["available"] = "yes"

    media = data.get("media_urls", [])
    if isinstance(media, str):
        media = _parse_media(media)
    data = {**data, "media_urls": json.dumps(media, ensure_ascii=False)}

    row = [str(data.get(col, "") or "") for col in PROPERTY_COLUMNS]
    ws.append_row(row, value_input_option="RAW")
    _props_cache = None  # invalidate cache so the new item shows immediately
    log.info("Added property %s", data["id"])
    return data
