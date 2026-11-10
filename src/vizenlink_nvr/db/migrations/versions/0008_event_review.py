"""event review state (acknowledge / resolve / hide)

Revision ID: 0008_event_review
Revises: 0007_mobile_pairing
Create Date: 2026-11-10 12:00:00.000000

Phase 10 (old VMS alert parity). Hiding an alert never deletes the event row,
so footage protection tied to the event (REC-04) is unaffected.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_event_review"
down_revision: str | None = "0007_mobile_pairing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("review_state", sa.Text(), nullable=False, server_default="new"))
        batch.add_column(sa.Column("reviewed_at", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("reviewed_by", sa.Text(), nullable=True))
        batch.add_column(sa.Column("hidden_at", sa.BigInteger(), nullable=True))
        batch.create_check_constraint(
            "ck_event_review_state", "review_state IN ('new', 'acknowledged', 'resolved')"
        )
        batch.create_index("ix_events_review_state", ["review_state"])


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.drop_index("ix_events_review_state")
        batch.drop_constraint("ck_event_review_state", type_="check")
        batch.drop_column("hidden_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("reviewed_at")
        batch.drop_column("review_state")
