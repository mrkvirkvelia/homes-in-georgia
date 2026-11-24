"""tax_declarations: «Декларации RS.ge» — the agent's monthly turnover from his bank statement and whether he filed the
small-business declaration on rs.ge (services/tax.py). Numbered 0039 because daily-rent-automation has its own 0038 after
0037 too: both follow 0037 and every deploy runs `alembic upgrade heads`, which applies parallel branches in any order.

Revision ID: 0039
Revises: 0037
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0039'
down_revision: Union[str, Sequence[str], None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_declarations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("turnover", sa.Numeric(14, 2), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period", name="tax_declarations_user_period_key"),
        sa.CheckConstraint("turnover >= 0", name="tax_declarations_turnover_check"),
        sa.CheckConstraint("extract(day from period) = 1", name="tax_declarations_period_check"),
    )
    op.create_index("tax_declarations_period_idx", "tax_declarations", ["period"])


def downgrade() -> None:
    op.drop_table("tax_declarations")
