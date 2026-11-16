"""Car operator role + removed users (Stanislav 11-16).

users.role / invites.role: 'car_operator' («Оператор авто») — like daily_rent_manager outside the level ladder, sees only
«Авто» (api/deps.current_user). users.deleted_at: a removed (inactive) user is hidden from every list and picker, his
objects went to «Платформа» (agent_id NULL); deals and leads keep him for the history and stats.

Revision ID: 0023
Revises: 0022
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = "role IN ('superadmin', 'admin', 'operator', 'agent', 'recruit', 'daily_rent_manager', 'car_operator')"
OLD = "role IN ('superadmin', 'admin', 'operator', 'agent', 'recruit', 'daily_rent_manager')"


def upgrade() -> None:
    for table, name in (("users", "users_role_check"), ("invites", "invites_role_check")):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, NEW)
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "deleted_at")
    op.execute("UPDATE invites SET revoked_at = now() WHERE role = 'car_operator' AND revoked_at IS NULL")
    op.execute("UPDATE invites SET role = 'recruit' WHERE role = 'car_operator'")
    op.execute("UPDATE users SET role = 'recruit', is_active = false WHERE role = 'car_operator'")
    for table, name in (("users", "users_role_check"), ("invites", "invites_role_check")):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, OLD)
