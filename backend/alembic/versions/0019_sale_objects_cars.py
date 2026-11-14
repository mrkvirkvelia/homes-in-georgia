"""sale_objects + cars: the site hge.ge's sale / new buildings / commercial-for-sale objects and cars (rent stays in properties)

Revision ID: 0019
Revises: 0018
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = "status IN ('draft', 'published', 'archived')"


def _common() -> list:
    ts = sa.DateTime(timezone=True)
    return [
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False), sa.Column("description", sa.Text),
        sa.Column("price", sa.Numeric(14, 2)), sa.Column("currency", sa.Text, nullable=False, server_default="USD"),
        sa.Column("lat", sa.Float), sa.Column("lng", sa.Float),
        sa.Column("is_exclusive", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("photos", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("video", sa.Text),
        sa.Column("post_url", sa.Text), sa.Column("site_id", sa.Text, unique=True),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"), sa.Column("published_at", ts),
        sa.Column("created_at", ts, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.func.now()),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
    ]


def upgrade() -> None:
    txt = lambda n, **kw: sa.Column(n, sa.Text, **kw)  # noqa: E731
    num = lambda n, t=sa.Integer: sa.Column(n, t)  # noqa: E731
    op.create_table(
        "sale_objects", *_common(),
        txt("service", nullable=False), txt("kind", nullable=False, server_default="apartment"), txt("headline"),
        txt("district"), txt("metro"), sa.Column("approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        num("rooms"), num("area", sa.Numeric(10, 2)), num("floor"), num("floors"),
        txt("building"), txt("condition"), txt("heating"), txt("completion"),
        sa.Column("amenities", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint(STATUSES, name="sale_objects_status_check"),
        sa.CheckConstraint("service IN ('sale', 'new', 'commercial')", name="sale_objects_service_check"),
    )
    op.create_index("sale_objects_status_idx", "sale_objects", ["status"])
    op.create_table(
        "cars", *_common(),
        txt("deal", nullable=False), txt("period"), num("deposit", sa.Numeric(12, 2)), num("year"),
        txt("gearbox"), txt("fuel"), txt("body"), num("seats"), num("mileage"), txt("pickup"),
        sa.CheckConstraint(STATUSES, name="cars_status_check"),
        sa.CheckConstraint("deal IN ('rent', 'sale')", name="cars_deal_check"),
    )
    op.create_index("cars_status_idx", "cars", ["status"])


def downgrade() -> None:
    op.drop_table("cars")
    op.drop_table("sale_objects")
