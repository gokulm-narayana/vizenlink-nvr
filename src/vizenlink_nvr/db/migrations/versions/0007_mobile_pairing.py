"""mobile pairing and paired devices schema

Revision ID: 0007_mobile_pairing
Revises: 0006_gallery_and_exports
Create Date: 2026-11-04 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_mobile_pairing"
down_revision: str | None = "0006_gallery_and_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paired_devices",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("device_id", sa.Text(), nullable=False),
        sa.Column("device_name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("paired_at", sa.BigInteger(), nullable=False),
        sa.Column("last_seen_at", sa.BigInteger(), nullable=False),
        sa.Column("access_token_expires_at", sa.BigInteger(), nullable=False),
        sa.Column("refresh_token_expires_at", sa.BigInteger(), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paired_devices_device_id", "paired_devices", ["device_id"])
    op.create_index("ix_paired_devices_user_id", "paired_devices", ["user_id"])
    op.create_index("ix_paired_devices_access_token", "paired_devices", ["access_token"], unique=True)
    op.create_index("ix_paired_devices_refresh_token", "paired_devices", ["refresh_token"], unique=True)
    op.create_index(
        "ix_paired_devices_access_token_expires_at",
        "paired_devices",
        ["access_token_expires_at"],
    )
    op.create_index(
        "ix_paired_devices_refresh_token_expires_at",
        "paired_devices",
        ["refresh_token_expires_at"],
    )
    op.create_index("ix_paired_devices_is_revoked", "paired_devices", ["is_revoked"])

    op.create_table(
        "qr_pairing_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pairing_code", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("claimed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("claimed_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_qr_pairing_sessions_pairing_code",
        "qr_pairing_sessions",
        ["pairing_code"],
        unique=True,
    )
    op.create_index("ix_qr_pairing_sessions_user_id", "qr_pairing_sessions", ["user_id"])
    op.create_index("ix_qr_pairing_sessions_expires_at", "qr_pairing_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_qr_pairing_sessions_expires_at", table_name="qr_pairing_sessions")
    op.drop_index("ix_qr_pairing_sessions_user_id", table_name="qr_pairing_sessions")
    op.drop_index("ix_qr_pairing_sessions_pairing_code", table_name="qr_pairing_sessions")
    op.drop_table("qr_pairing_sessions")

    op.drop_index("ix_paired_devices_is_revoked", table_name="paired_devices")
    op.drop_index("ix_paired_devices_refresh_token_expires_at", table_name="paired_devices")
    op.drop_index("ix_paired_devices_access_token_expires_at", table_name="paired_devices")
    op.drop_index("ix_paired_devices_refresh_token", table_name="paired_devices")
    op.drop_index("ix_paired_devices_access_token", table_name="paired_devices")
    op.drop_index("ix_paired_devices_user_id", table_name="paired_devices")
    op.drop_index("ix_paired_devices_device_id", table_name="paired_devices")
    op.drop_table("paired_devices")
