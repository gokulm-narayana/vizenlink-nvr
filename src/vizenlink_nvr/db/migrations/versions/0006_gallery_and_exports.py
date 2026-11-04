"""gallery items and exports schema

Revision ID: 0006_gallery_and_exports
Revises: 0005_events_and_protection
Create Date: 2026-11-04 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_gallery_and_exports"
down_revision: str | None = "0005_events_and_protection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gallery_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("camera_serial", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["camera_serial"], ["camera.serial"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "item_type IN ('snapshot', 'manual_clip', 'export_clip')",
            name="ck_gallery_item_type",
        ),
    )
    op.create_index(
        "ix_gallery_items_camera_captured",
        "gallery_items",
        ["camera_serial", "captured_at"],
    )
    op.create_index(
        "ix_gallery_items_type",
        "gallery_items",
        ["item_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_gallery_items_type", table_name="gallery_items")
    op.drop_index("ix_gallery_items_camera_captured", table_name="gallery_items")
    op.drop_table("gallery_items")
