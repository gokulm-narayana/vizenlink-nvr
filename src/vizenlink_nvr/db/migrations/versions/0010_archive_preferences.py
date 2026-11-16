"""Preserve removed camera identities and store account display preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0010_archive_preferences"
down_revision = "0009_stream_tls_pin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("camera", sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("theme", sa.Text(), nullable=False, server_default="light"))
    op.add_column("users", sa.Column("view_mode", sa.Text(), nullable=False, server_default="simple"))


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM camera WHERE archived LIMIT 1")).first():
        raise RuntimeError("Restore archived cameras before downgrading to the live-only registry.")
    op.drop_column("users", "view_mode")
    op.drop_column("users", "theme")
    op.drop_column("camera", "archived")
