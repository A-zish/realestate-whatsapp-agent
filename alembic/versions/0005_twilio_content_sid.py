"""WhatsApp ContentSid for Twilio trial / template-first send.

Revision ID: 5e92c1d3f4a7
Revises: 4d81b0c2e5f6
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op

revision = "5e92c1d3f4a7"
down_revision = "4d81b0c2e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("twilio_content_sid", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "twilio_content_sid")
