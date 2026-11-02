"""recording core schema

Revision ID: 0003_recording_core
Revises: 0002_camera_registry
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_recording_core"
down_revision: str | None = "0002_camera_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recording_settings",
        sa.Column("camera_serial", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False, server_default="continuous"),
        sa.Column("schedule_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("audio_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("retention_max_gb", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["camera_serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("camera_serial"),
        sa.CheckConstraint(
            "mode IN ('continuous', 'scheduled', 'event', 'off')",
            name="ck_recording_settings_mode",
        ),
    )

    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_serial", sa.Text(), nullable=False),
        sa.Column("stream_type", sa.Text(), nullable=False, server_default="main"),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("start_time", sa.BigInteger(), nullable=False),
        sa.Column("end_time", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("protection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["camera_serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('active', 'missing', 'truncated')",
            name="ck_segment_status",
        ),
    )
    op.create_index("ix_segments_camera_serial", "segments", ["camera_serial"])
    op.create_index("ix_segments_file_path", "segments", ["file_path"], unique=True)
    op.create_index("ix_segments_start_time", "segments", ["start_time"])
    op.create_index("ix_segments_end_time", "segments", ["end_time"])

    op.create_table(
        "storage_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("allow_system_disk", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "reserve_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default="10737418240",
        ),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("storage_settings")
    op.drop_index("ix_segments_end_time", table_name="segments")
    op.drop_index("ix_segments_start_time", table_name="segments")
    op.drop_index("ix_segments_file_path", table_name="segments")
    op.drop_index("ix_segments_camera_serial", table_name="segments")
    op.drop_table("segments")
    op.drop_table("recording_settings")

