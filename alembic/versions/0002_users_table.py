"""Replace external-auth `profiles` with a self-hosted `users` table.

Revision ID: 2b71c0f4a9e1
Revises: 16acfffca66c
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "2b71c0f4a9e1"
down_revision = "16acfffca66c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
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
    op.create_index("ix_users_account_id", "users", ["account_id"])
    # `profiles` only ever linked to external auth user ids, which no longer
    # exist now that logins live in `users`. No data worth migrating.
    op.drop_table("profiles")


def downgrade() -> None:
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
    op.drop_table("users")
