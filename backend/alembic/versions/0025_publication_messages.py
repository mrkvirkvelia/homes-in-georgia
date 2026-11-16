"""Every message of our Telegram post is kept, so a repost / «Сдано» can delete the whole post (Stanislav 11-16).

property_publications.messages: {"chat": …, "ids": [message ids]} — the album, the originals and the owner card
(notify.publish_post); delete_error: why deleting it failed (shown on the object card).

Revision ID: 0025
Revises: 0024
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("property_publications", sa.Column("messages", JSONB))
    op.add_column("property_publications", sa.Column("delete_error", sa.Text))


def downgrade() -> None:
    op.drop_column("property_publications", "delete_error")
    op.drop_column("property_publications", "messages")
