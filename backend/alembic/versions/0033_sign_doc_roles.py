"""«Договор между сторонами» (Irakli 11-18: owner ↔ client, no company signature): each outside signer has a role label
(«Собственник», «Клиент»), shown on the link list and the signing record page.

Revision ID: 0033
Revises: 0032
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sign_doc_signers", sa.Column("role", sa.Text))


def downgrade() -> None:
    op.drop_column("sign_doc_signers", "role")
