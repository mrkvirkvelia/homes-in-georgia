"""«Похожие объекты» everywhere (Stanislav 11-17): similar_decisions, an agent's «Дубль» / «Не дубль» on a pair
(«l:<listing id>» / «p:<object id>», a < b), so a pair he called different is not shown again. (The objects' photo
hashes are property_media.dhash, migration 0030.)

Revision ID: 0031
Revises: 0030
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0031'
down_revision: Union[str, Sequence[str], None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "similar_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("a", sa.Text, nullable=False),
        sa.Column("b", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("a", "b", name="similar_decisions_pair_uq"),
        sa.CheckConstraint("verdict IN ('same', 'different')", name="similar_decisions_verdict_check"),
    )


def downgrade() -> None:
    op.drop_table("similar_decisions")
