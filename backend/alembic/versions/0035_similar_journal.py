"""Duplicate score (David 11-19): «Нужна проверка» as a third verdict on a pair, and similar_journal — every operator
decision on a pair (who, when, the pair, the score, its features) for calibrating the weights (app/dup_eval.py).

Revision ID: 0035
Revises: 0034
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0035'
down_revision: Union[str, Sequence[str], None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("similar_decisions_verdict_check", "similar_decisions", type_="check")
    op.create_check_constraint("similar_decisions_verdict_check", "similar_decisions", "verdict IN ('same', 'different', 'review')")
    op.create_table(
        "similar_journal",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("a", sa.Text, nullable=False),
        sa.Column("b", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("prev", sa.Text),
        sa.Column("score", sa.Float),
        sa.Column("level", sa.Text),
        sa.Column("features", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("similar_journal_pair", "similar_journal", ["a", "b"])


def downgrade() -> None:
    op.drop_table("similar_journal")
    op.execute("DELETE FROM similar_decisions WHERE verdict = 'review'")
    op.drop_constraint("similar_decisions_verdict_check", "similar_decisions", type_="check")
    op.create_check_constraint("similar_decisions_verdict_check", "similar_decisions", "verdict IN ('same', 'different')")
