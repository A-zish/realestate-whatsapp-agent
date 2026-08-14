"""Postgres access — the multi-tenant datastore (replaces app/sheets.py).

Every function that touches leads or properties takes `account_id` as its
first argument and only ever reads/writes rows scoped to that account — this
is the entire tenant-isolation guarantee for the whole app. There is no
function here that can read across accounts (except the account-lookup
helpers themselves, which by definition operate on the accounts table).

Public API mirrors the old app/sheets.py shape so app/main.py and
app/agent.py stay easy to read, but everything is account-scoped:
    get_lead(account_id, phone)                  -> dict | None
    get_all_leads(account_id)                     -> list[dict]
    upsert_lead(account_id, data)                  -> dict
    update_lead_fields(account_id, phone, fields)  -> dict
    get_properties(account_id, only_available)     -> list[dict]
    add_property(account_id, data)                 -> dict
    get_account_by_slug(slug) / by_id(id) / by_twilio_number(to)
    create_account(agency_name) / update_account(account_id, fields)
    get_account_id_for_user(user_id) / link_user_to_account(user_id, account_id)
"""
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import config
from app.models import Account, Lead, Profile, Property
from app.utils import normalize_phone

log = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        config.require("DATABASE_URL")
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _engine


def _session() -> Session:
    return Session(_get_engine())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "agency"


# --- Accounts ----------------------------------------------------------------


def _account_to_dict(a: Account) -> dict:
    return {
        "id": str(a.id),
        "slug": a.slug,
        "agency_name": a.agency_name,
        "agent_name": a.agent_name,
        "city": a.city,
        "custom_instructions": a.custom_instructions,
        "twilio_whatsapp_from": a.twilio_whatsapp_from,
    }


def create_account(agency_name: str, agent_name: str = "Priya", city: str = "Jaipur") -> dict:
    """Create a new tenant. Slug is derived from the agency name, made unique."""
    with _session() as session:
        base_slug = slugify(agency_name)
        slug = base_slug
        while session.scalar(select(Account).where(Account.slug == slug)) is not None:
            slug = f"{base_slug}-{secrets.token_hex(2)}"

        account = Account(
            id=uuid.uuid4(), slug=slug, agency_name=agency_name,
            agent_name=agent_name, city=city, custom_instructions="",
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        log.info("Created account %s (%s)", account.slug, account.id)
        return _account_to_dict(account)


def get_account_by_slug(slug: str) -> dict | None:
    with _session() as session:
        account = session.scalar(select(Account).where(Account.slug == slug))
        return _account_to_dict(account) if account else None


def get_account_by_id(account_id) -> dict | None:
    with _session() as session:
        account = session.get(Account, account_id)
        return _account_to_dict(account) if account else None


def get_account_by_twilio_number(to_number: str) -> dict | None:
    """Resolve which tenant owns an inbound WhatsApp number (webhook routing)."""
    with _session() as session:
        account = session.scalar(
            select(Account).where(Account.twilio_whatsapp_from == to_number)
        )
        if account:
            return _account_to_dict(account)
        # Fallback: while only one account has a WhatsApp number configured
        # at all (pre-multi-number-onboarding), route everything to it.
        only = session.scalars(select(Account).where(Account.twilio_whatsapp_from.isnot(None))).all()
        if len(only) == 1:
            return _account_to_dict(only[0])
        return None


def update_account(account_id, fields: dict) -> dict:
    """Partial update of an account's branding/settings."""
    allowed = {"agency_name", "agent_name", "city", "custom_instructions", "twilio_whatsapp_from"}
    with _session() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"No such account: {account_id}")
        for key, value in fields.items():
            if key in allowed:
                setattr(account, key, value)
        session.commit()
        session.refresh(account)
        return _account_to_dict(account)


# --- Profiles (user -> account link) -----------------------------------------


def get_account_id_for_user(user_id) -> str | None:
    with _session() as session:
        profile = session.get(Profile, user_id)
        return str(profile.account_id) if profile else None


def link_user_to_account(user_id, account_id) -> None:
    with _session() as session:
        session.add(Profile(user_id=user_id, account_id=account_id))
        session.commit()


# --- Leads ---------------------------------------------------------------


def _lead_to_dict(lead: Lead) -> dict:
    return {
        "phone": lead.phone,
        "name": lead.name,
        "source": lead.source,
        "status": lead.status,
        "score": lead.score,
        "stage": lead.stage,
        "intent": lead.intent,
        "location_pref": lead.location_pref,
        "property_type": lead.property_type,
        "budget": lead.budget,
        "timeline": lead.timeline,
        "last_message": lead.last_message,
        "history_json": lead.history_json or [],
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else "",
    }


_LEAD_FIELDS = (
    "name", "source", "status", "score", "stage", "intent", "location_pref",
    "property_type", "budget", "timeline", "last_message", "history_json",
)


def get_lead(account_id, phone: str) -> dict | None:
    phone = normalize_phone(phone)
    with _session() as session:
        lead = session.scalar(
            select(Lead).where(Lead.account_id == account_id, Lead.phone == phone)
        )
        return _lead_to_dict(lead) if lead else None


def get_all_leads(account_id) -> list[dict]:
    with _session() as session:
        leads = session.scalars(
            select(Lead).where(Lead.account_id == account_id).order_by(Lead.updated_at)
        ).all()
        return [_lead_to_dict(lead) for lead in leads]


def upsert_lead(account_id, data: dict) -> dict:
    """Create a lead row, or merge fields into an existing one (key = phone within the account)."""
    if not data.get("phone"):
        raise ValueError("upsert_lead requires a 'phone' field")
    phone = normalize_phone(data["phone"])

    with _session() as session:
        lead = session.scalar(
            select(Lead).where(Lead.account_id == account_id, Lead.phone == phone)
        )
        if lead is None:
            lead = Lead(id=uuid.uuid4(), account_id=account_id, phone=phone)
            session.add(lead)

        for key in _LEAD_FIELDS:
            if key in data:
                setattr(lead, key, data[key])

        session.commit()
        session.refresh(lead)
        log.info("Upserted lead %s (account=%s)", phone, account_id)
        return _lead_to_dict(lead)


def update_lead_fields(account_id, phone: str, fields: dict) -> dict:
    """Partial update of specific columns for an existing (or new) lead."""
    phone = normalize_phone(phone)
    return upsert_lead(account_id, {**fields, "phone": phone})


# --- Properties ----------------------------------------------------------


def _property_to_dict(p: Property) -> dict:
    media = p.media_urls or []
    return {
        "id": str(p.id),
        "display_id": p.display_id,
        "title": p.title,
        "type": p.type,
        "location": p.location,
        "price": p.price,
        "media_urls": media,
        "media": media,
        "available": p.available,
    }


def get_properties(account_id, only_available: bool = True) -> list[dict]:
    with _session() as session:
        stmt = select(Property).where(Property.account_id == account_id)
        if only_available:
            stmt = stmt.where(Property.available.notin_(["no", "false", "0", "sold"]))
        rows = session.scalars(stmt.order_by(Property.created_at)).all()
        return [_property_to_dict(p) for p in rows]


def add_property(account_id, data: dict) -> dict:
    with _session() as session:
        if not data.get("display_id"):
            existing = session.scalars(
                select(Property).where(Property.account_id == account_id)
            ).all()
            data["display_id"] = f"P-{len(existing) + 1:03d}"

        prop = Property(
            id=uuid.uuid4(),
            account_id=account_id,
            display_id=data.get("display_id", ""),
            title=data["title"],
            type=data.get("type", ""),
            location=data.get("location", ""),
            price=data.get("price", ""),
            media_urls=data.get("media_urls") or [],
            available=data.get("available") or "yes",
        )
        session.add(prop)
        session.commit()
        session.refresh(prop)
        log.info("Added property %s (account=%s)", prop.display_id, account_id)
        return _property_to_dict(prop)
