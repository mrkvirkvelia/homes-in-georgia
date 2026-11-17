"""«Похожие объекты» everywhere (Stanislav 11-17): properties.photo_hashes (dHash of the object's own photos, NULL =
not computed yet; the worker fills old objects, an upload hashes new photos) so an outside ad with the same photos is
found even when the object was shot by our agent; similar_decisions: an agent's «Дубль» / «Не дубль» on a pair
(«l:<listing id>» / «p:<object id>», a < b), so a pair he called different is not shown again.

Revision ID: 0029
Revises: 0028
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("photo_hashes", sa.Text))
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
    op.drop_column("properties", "photo_hashes")
