"""The owner's exclusive sign page keeps a draft (Stanislav 11-16: «в таких ссылках всегда сохранялось всё как черновик»).

properties.sign_draft: what the owner typed on /sign/<token> (name, ID, phone, code, language, the NAPR application) and
the files he already gave (the extract by its link / PDF, the passport — private storage keys). Reopening the link
continues it; cleared once he signs.

Revision ID: 0024
Revises: 0023
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("sign_draft", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("properties", "sign_draft")
