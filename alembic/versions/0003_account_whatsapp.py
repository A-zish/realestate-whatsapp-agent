"""Per-account WhatsApp credentials (bring-your-own Twilio).

Revision ID: 3c92ae61b7d4
Revises: 2b71c0f4a9e1
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "3c92ae61b7d4"
down_revision = "2b71c0f4a9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("twilio_account_sid", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("twilio_auth_token_enc", sa.Text(), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("whatsapp_status", sa.Text(), nullable=False, server_default="not_connected"),
    )
    # Any account that already has a number is on the shared sandbox.
    op.execute(
        "UPDATE accounts SET whatsapp_status = 'sandbox' "
        "WHERE twilio_whatsapp_from IS NOT NULL AND twilio_whatsapp_from <> ''"
    )


def downgrade() -> None:
    op.drop_column("accounts", "whatsapp_status")
    op.drop_column("accounts", "twilio_auth_token_enc")
    op.drop_column("accounts", "twilio_account_sid")
