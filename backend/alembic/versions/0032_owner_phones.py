"""An owner holds any number of phones (David + Irakli 11-18: the number from the ad and the one the person gave on the
call, «сестра», a foreign one): owners.phones = [{phone, norm, note}], the main first. owners.phone / phone_norm stay the
main number, so old readers and exports keep working. Existing phones are copied over.

Revision ID: 0032
Revises: 0031
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("owners", sa.Column("phones", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.execute("""UPDATE owners SET phones = jsonb_build_array(jsonb_build_object('phone', phone, 'norm', phone_norm, 'note', NULL))
                  WHERE phone ~ '[0-9]'""")
    op.create_index("owners_phones_idx", "owners", ["phones"], postgresql_using="gin", postgresql_ops={"phones": "jsonb_path_ops"})


def downgrade() -> None:
    op.drop_index("owners_phones_idx", table_name="owners")
    op.drop_column("owners", "phones")
