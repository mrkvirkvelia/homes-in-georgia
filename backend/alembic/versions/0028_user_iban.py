"""users.iban_gel / iban_usd: the agent's bank accounts for the platform agreement, filled by the agent in his cabinet
(«Реквизиты для соглашения»), prefill the NDA and update an unsigned one (Stanislav 11-16).

Revision ID: 0028
Revises: 0027
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("iban_gel", sa.Text))
    op.add_column("users", sa.Column("iban_usd", sa.Text))


def downgrade() -> None:
    op.drop_column("users", "iban_usd")
    op.drop_column("users", "iban_gel")
