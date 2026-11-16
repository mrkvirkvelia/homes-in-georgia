"""users.ie_number: the agent's ИП (ი/მ) registration number, a party detail of the platform agreement (Stanislav 11-16).

Revision ID: 0026
Revises: 0025
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ie_number", sa.Text))


def downgrade() -> None:
    op.drop_column("users", "ie_number")
