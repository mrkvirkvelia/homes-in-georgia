"""property_media.dhash: a 64-bit difference hash of every object photo (bot/ingest.py dhash), so the matcher compares a
new ad's photos with the photos of our objects, not only with the ads linked to them (David 11-17: «по фото видно, что
это та же квартира, а он не мэчит»). Signed bigint: the hash's top bit wraps.

Revision ID: 0030
Revises: 0029
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0030'
down_revision: Union[str, Sequence[str], None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("property_media", sa.Column("dhash", sa.BigInteger))


def downgrade() -> None:
    op.drop_column("property_media", "dhash")
