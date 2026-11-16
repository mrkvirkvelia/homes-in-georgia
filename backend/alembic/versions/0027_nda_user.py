"""agent_ndas.user_id: an NDA made for a team member (Пользователи → NDA → «В команде без соглашения»); users.personal_id:
the agreement's personal number, kept in the profile (prefills the NDA, written back on signing) (Stanislav 11-16).

Revision ID: 0027
Revises: 0026
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_ndas", sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.create_index("agent_ndas_user_idx", "agent_ndas", ["user_id"])
    op.add_column("users", sa.Column("personal_id", sa.Text))


def downgrade() -> None:
    op.drop_column("users", "personal_id")
    op.drop_index("agent_ndas_user_idx", "agent_ndas")
    op.drop_column("agent_ndas", "user_id")
