"""per-stream TLS certificate pin

Revision ID: 0009_stream_tls_pin
Revises: 0008_event_review
Create Date: 2026-11-11 18:00:00.000000

VizenLink cameras present a different self-signed certificate on the RTSPS ports
(554/555) than on HTTPS (443). Pinning the HTTPS certificate for the video source
made MediaMTX reject every RTSPS connection, so cameras never streamed or recorded.
Each stream now carries its own pin (null until the recorder pins it).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_stream_tls_pin"
down_revision: str | None = "0008_event_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("camera_stream") as batch:
        batch.add_column(sa.Column("tls_fingerprint_sha256", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("camera_stream") as batch:
        batch.drop_column("tls_fingerprint_sha256")
