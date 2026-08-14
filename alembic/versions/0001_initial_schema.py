"""Initial multi-tenant schema: accounts, profiles, leads, properties.

Revision ID: 16acfffca66c
Revises:
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "16acfffca66c"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("agency_name", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False, server_default="Priya"),
        sa.Column("city", sa.Text(), nullable=False, server_default="Jaipur"),
        sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("twilio_whatsapp_from", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="new"),
        sa.Column("score", sa.Text(), nullable=False, server_default=""),
        sa.Column("stage", sa.Text(), nullable=False, server_default=""),
        sa.Column("intent", sa.Text(), nullable=False, server_default=""),
        sa.Column("location_pref", sa.Text(), nullable=False, server_default=""),
        sa.Column("property_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("budget", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeline", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("history_json", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("account_id", "phone", name="uq_leads_account_phone"),
    )
    op.create_index("ix_leads_account_id", "leads", ["account_id"])

    op.create_table(
        "properties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.Text(), nullable=False, server_default=""),
        sa.Column("price", sa.Text(), nullable=False, server_default=""),
        sa.Column("media_urls", JSONB(), nullable=False, server_default="[]"),
        sa.Column("available", sa.Text(), nullable=False, server_default="yes"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_properties_account_id", "properties", ["account_id"])


def downgrade() -> None:
    op.drop_table("properties")
    op.drop_table("leads")
    op.drop_table("profiles")
    op.drop_table("accounts")
