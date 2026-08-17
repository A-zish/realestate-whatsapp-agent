"""Lead WhatsApp delivery diagnostics (last SID / error).

Revision ID: 6f03d2e4a5b8
Revises: 5e92c1d3f4a7
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op

revision = "6f03d2e4a5b8"
down_revision = "5e92c1d3f4a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("last_whatsapp_sid", sa.Text(), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("last_whatsapp_error", sa.Text(), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("last_whatsapp_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "last_whatsapp_at")
    op.drop_column("leads", "last_whatsapp_error")
    op.drop_column("leads", "last_whatsapp_sid")
