"""site_events: hge.ge's own visitor counter (was a Google Sheet behind an Apps Script)

Revision ID: 0020
Revises: 0019
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        *[sa.Column(c, sa.Text, nullable=c not in ("visitor", "session", "type"))
          for c in ("visitor", "session", "type", "path", "listing", "service", "agent", "source", "medium", "campaign",
                    "lang", "theme", "device")],
        sa.Column("new", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_site_events_at", "site_events", ["at"])


def downgrade() -> None:
    op.drop_table("site_events")
