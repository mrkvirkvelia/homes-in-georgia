"""listings.status «copy»: a myhome ad found for an object by services/myhome_copies.py (David 11-22) — compared in
«Похожие», never shown to clients, not marked gone by the parser's sync.

Revision ID: 0036
Revises: 0035
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0036'
down_revision: Union[str, Sequence[str], None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("listings_status_check", "listings", type_="check")
    op.create_check_constraint("listings_status_check", "listings",
                               "status IN ('published', 'pending_review', 'rejected', 'gone', 'copy')")


def downgrade() -> None:
    op.execute("UPDATE listings SET status = 'gone' WHERE status = 'copy'")
    op.drop_constraint("listings_status_check", "listings", type_="check")
    op.create_check_constraint("listings_status_check", "listings", "status IN ('published', 'pending_review', 'rejected', 'gone')")
