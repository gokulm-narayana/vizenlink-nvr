"""camera registry schema

Revision ID: 0002_camera_registry
Revises: 0001_initial
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_camera_registry"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera",
        sa.Column("serial", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("https_port", sa.Integer(), nullable=False, server_default="443"),
        sa.Column("mac", sa.Text(), nullable=False, server_default=""),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.Text(), nullable=False, server_default=""),
        sa.Column("group_tag", sa.Text(), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.Text(), nullable=False, server_default=""),
        sa.Column("firmware_version", sa.Text(), nullable=False, server_default=""),
        sa.Column("hardware_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("tls_fingerprint_sha256", sa.Text(), nullable=False),
        sa.Column("camera_id_check", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("added_at", sa.BigInteger(), nullable=False),
        sa.Column("host_updated_at", sa.BigInteger(), nullable=False),
        sa.Column("identity_synced_at", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("serial"),
        sa.CheckConstraint(
            "state IN ('active', 'auth_failed', 'tls_changed', 'unreachable')",
            name="ck_camera_state",
        ),
    )

    op.create_table(
        "camera_credential",
        sa.Column("serial", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("enc_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("serial"),
    )

    op.create_table(
        "camera_capabilities",
        sa.Column("serial", sa.Text(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column("probed_at", sa.BigInteger(), nullable=False),
        sa.Column("firmware_version_at_probe", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("serial"),
    )

    op.create_table(
        "camera_stream",
        sa.Column("serial", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("profile_token", sa.Text(), nullable=False),
        sa.Column("profile_name", sa.Text(), nullable=False),
        sa.Column("venc_token", sa.Text(), nullable=False),
        sa.Column("codec", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("transport", sa.Text(), nullable=False),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("sub_is_main", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("probed_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("serial", "role"),
        sa.CheckConstraint("role IN ('main', 'sub')", name="ck_camera_stream_role"),
        sa.CheckConstraint(
            "source IN ('nuraeye', 'onvif_fallback')",
            name="ck_camera_stream_source",
        ),
    )


def downgrade() -> None:
    op.drop_table("camera_stream")
    op.drop_table("camera_capabilities")
    op.drop_table("camera_credential")
    op.drop_table("camera")
