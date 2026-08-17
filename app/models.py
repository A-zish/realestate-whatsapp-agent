"""SQLAlchemy ORM models — the multi-tenant datastore (Postgres via Supabase).

Every table that holds business data carries an `account_id` (tenant). There
is no query path in app/db.py that reads or writes leads/properties without
one — that's the entire tenant-isolation guarantee.

Logins live in `users` (PBKDF2 hashes). See app/auth.py.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Account(Base):
    """One real estate agency = one account (tenant)."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    agency_name: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False, default="Priya")
    city: Mapped[str] = mapped_column(Text, nullable=False, default="Jaipur")
    custom_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # --- WhatsApp channel (per agency) ---
    # The number leads see. Also how an inbound Twilio webhook is routed back
    # to the right account.
    twilio_whatsapp_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    # An agency can bring their own Twilio account. When these are set we send
    # as them; when they're empty we fall back to the platform's shared
    # sandbox credentials (fine for demos, not for production volume).
    twilio_account_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fernet-encrypted — never stored or logged in plaintext. See app/crypto.py.
    twilio_auth_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Twilio Content Template SID (HX…) required on trial WhatsApp / first outbound.
    twilio_content_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    # not_connected | sandbox | connected
    whatsapp_status: Mapped[str] = mapped_column(Text, nullable=False, default="not_connected")
    ingest_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_now)


class User(Base):
    """A login for one account. Passwords are hashed with PBKDF2-HMAC-SHA256
    (Python stdlib) — see app/auth.py. We deliberately do NOT use an external
    auth service: it added a fragile network hop for something the stdlib
    does well, and cost us email-confirmation friction, signup rate limits,
    and an opaque encoding crash in production."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Lead(Base):
    """One row per lead, scoped to the account that owns them."""

    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("account_id", "phone", name="uq_leads_account_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    score: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stage: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location_pref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    property_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    budget: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timeline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    history_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    score_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    campaign: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gclid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # pending | in_conversation | scored
    qualification_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # Last outbound WhatsApp attempt (Twilio SID or friendly error).
    last_whatsapp_sid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_whatsapp_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_whatsapp_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Property(Base):
    """One row per property in an account's inventory."""

    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price: Mapped[str] = mapped_column(Text, nullable=False, default="")
    media_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    available: Mapped[str] = mapped_column(Text, nullable=False, default="yes")
    created_at: Mapped[datetime] = mapped_column(default=_now)
