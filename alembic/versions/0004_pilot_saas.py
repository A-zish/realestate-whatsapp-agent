"""Pilot SaaS columns: COLD reasons, Ads ingest fields, onboarding, ingest token.

Revision ID: 4d81b0c2e5f6
Revises: 3c92ae61b7d4
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op

revision = "4d81b0c2e5f6"
down_revision = "3c92ae61b7d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("ingest_token_hash", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE accounts SET onboarding_completed_at = created_at WHERE onboarding_completed_at IS NULL")

    op.add_column("leads", sa.Column("score_reason", sa.Text(), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("campaign", sa.Text(), nullable=False, server_default=""))
    op.add_column("leads", sa.Column("gclid", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "leads",
        sa.Column("qualification_status", sa.Text(), nullable=False, server_default="pending"),
    )
    op.execute(
        "UPDATE leads SET qualification_status = 'scored' "
        "WHERE score IS NOT NULL AND btrim(score) <> ''"
    )
    op.execute(
        "UPDATE leads SET qualification_status = 'in_conversation' "
        "WHERE (qualification_status = 'pending') AND last_message IS NOT NULL AND btrim(last_message) <> ''"
    )


def downgrade() -> None:
    op.drop_column("leads", "qualification_status")
    op.drop_column("leads", "gclid")
    op.drop_column("leads", "campaign")
    op.drop_column("leads", "score_reason")
    op.drop_column("accounts", "onboarding_completed_at")
    op.drop_column("accounts", "ingest_token_hash")
