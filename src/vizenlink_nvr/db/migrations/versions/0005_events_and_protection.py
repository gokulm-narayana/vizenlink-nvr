"""events and protection schema

Revision ID: 0005_events_and_protection
Revises: 0004_auth_and_audit
Create Date: 2026-11-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_events_and_protection"
down_revision: str | None = "0004_auth_and_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create events table
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_serial", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="onvif_pullpoint"),
        sa.Column("start_time", sa.BigInteger(), nullable=False),
        sa.Column("end_time", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_path", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("clock_sync_state", sa.Text(), nullable=False, server_default="synced"),
        sa.Column("raw_topic", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["camera_serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "clock_sync_state IN ('synced', 'uncertain', 'drift_detected')",
            name="ck_event_clock_sync_state",
        ),
    )
    op.create_index("ix_events_camera_serial", "events", ["camera_serial"])
    op.create_index("ix_events_start_time", "events", ["start_time"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_is_locked", "events", ["is_locked"])

    # 2. Create event_subscriptions table
    op.create_table(
        "event_subscriptions",
        sa.Column("camera_serial", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("subscription_url", sa.Text(), nullable=True),
        sa.Column("last_event_at", sa.BigInteger(), nullable=True),
        sa.Column("last_renewed_at", sa.BigInteger(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("clock_drift_seconds", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["camera_serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("camera_serial"),
        sa.CheckConstraint(
            "state IN ('idle', 'subscribing', 'active', 'reconnecting', 'failed')",
            name="ck_event_subscription_state",
        ),
    )

    # 3. Add pre_roll_seconds and post_roll_seconds to recording_settings
    with op.batch_alter_table("recording_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("pre_roll_seconds", sa.Integer(), nullable=False, server_default="10")
        )
        batch_op.add_column(
            sa.Column("post_roll_seconds", sa.Integer(), nullable=False, server_default="10")
        )


def downgrade() -> None:
    with op.batch_alter_table("recording_settings", schema=None) as batch_op:
        batch_op.drop_column("post_roll_seconds")
        batch_op.drop_column("pre_roll_seconds")

    op.drop_table("event_subscriptions")
    op.drop_index("ix_events_is_locked", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_start_time", table_name="events")
    op.drop_index("ix_events_camera_serial", table_name="events")
    op.drop_table("events")

