"""SQLAlchemy ORM models — the multi-tenant datastore (Postgres via Supabase).

Every table that holds business data carries an `account_id` (tenant). There
is no query path in app/db.py that reads or writes leads/properties without
one — that's the entire tenant-isolation guarantee.

`profiles` links a Supabase Auth user (their `auth.users.id`) to exactly one
account. Password hashing, signup/login verification, and password-reset
emails are handled by Supabase Auth itself (see app/auth.py) — this app
never stores or checks a password directly.
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
    # Nullable: real per-tenant WhatsApp provisioning is a later phase. Until
    # then, at most one account may hold the single shared sandbox number.
    twilio_whatsapp_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Profile(Base):
    """Links a Supabase Auth user to the one account they belong to."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
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
