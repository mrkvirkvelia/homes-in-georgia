"""«Посуточная аренда» inside the CRM: ApartFlow's tables (models/daily_rent.py), no more iframe.

Self-contained: only new dr_* tables, nothing existing changes. Renumber on merge if another 0021 lands first.

Revision ID: 0021
Revises: 0020
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("dr_blocks", "dr_channels", "dr_staff", "dr_cleanings", "dr_expenses", "dr_bookings", "dr_apartments")


def _row():
    return [sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("legacy_id", sa.Text, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True))]


def _fk(name, table, nullable=True, ondelete="RESTRICT"):
    return sa.Column(name, sa.Integer, sa.ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable)


def _jsonb(name, default):
    return sa.Column(name, JSONB, nullable=False, server_default=sa.text(f"'{default}'::jsonb"))


def upgrade() -> None:
    T, N, B, D = sa.Text, sa.Numeric, sa.Boolean, sa.Date
    op.create_table(
        "dr_apartments", *_row(),
        sa.Column("name", T, nullable=False), sa.Column("address", T), sa.Column("owner_name", T),
        sa.Column("owner_contact", T), sa.Column("owner_account", T),
        sa.Column("platform_pct", N(5, 2), nullable=False, server_default="20"),
        _jsonb("platforms", '["Airbnb", "Booking"]'),
        sa.Column("status", T, nullable=False, server_default="free"),
        sa.Column("active", B, nullable=False, server_default=sa.text("true")),
        sa.Column("rooms", sa.Integer), sa.Column("notes", T), _jsonb("util_rates", "{}"), _jsonb("photos", "[]"),
        sa.Column("price_night", N(12, 2)), sa.Column("currency", T, nullable=False, server_default="USD"),
        sa.Column("description", T), sa.Column("district", T),
        sa.CheckConstraint("status IN ('free', 'busy', 'clean', 'tech')", name="dr_apartments_status_check"),
        sa.CheckConstraint("platform_pct >= 0 AND platform_pct <= 100", name="dr_apartments_pct_check"),
    )
    op.create_table(
        "dr_bookings", *_row(), _fk("apartment_id", "dr_apartments", False),
        sa.Column("platform", T, nullable=False, server_default="Airbnb"), sa.Column("guest_name", T),
        sa.Column("check_in", D), sa.Column("check_out", D), sa.Column("gross", N(12, 2)),
        sa.Column("currency", T, nullable=False, server_default="USD"),
        sa.Column("tax_pct", N(5, 2), nullable=False, server_default="0"), sa.Column("booking_fee", N(12, 2)),
        sa.Column("platform_pct", N(5, 2), nullable=False, server_default="20"),
        sa.Column("payment_status", T, nullable=False, server_default="received"),
        sa.Column("paid_out", B, nullable=False, server_default=sa.text("false")), sa.Column("paid_out_at", D),
        sa.Column("assigned_staff", T), sa.Column("comment", T), _jsonb("extra", "{}"),
        sa.CheckConstraint("payment_status IN ('received', 'pending', 'partial')", name="dr_bookings_payment_check"),
        sa.CheckConstraint("currency IN ('USD', 'GEL')", name="dr_bookings_currency_check"),
    )
    op.create_index("dr_bookings_apt_idx", "dr_bookings", ["apartment_id", "check_in"])
    op.create_table(
        "dr_expenses", *_row(), _fk("booking_id", "dr_bookings"), _fk("apartment_id", "dr_apartments"),
        sa.Column("category", T, nullable=False, server_default="other"), sa.Column("amount", N(12, 2)),
        sa.Column("currency", T, nullable=False, server_default="GEL"),
        sa.Column("payer", T, nullable=False, server_default="platform"),
        sa.Column("comment", T), sa.Column("date", D), sa.Column("created_by", T), _jsonb("extra", "{}"),
        sa.CheckConstraint("payer IN ('platform', 'owner')", name="dr_expenses_payer_check"),
    )
    op.create_index("dr_expenses_booking_idx", "dr_expenses", ["booking_id"])
    op.create_table(
        "dr_cleanings", *_row(), _fk("apartment_id", "dr_apartments", False),
        sa.Column("cleaner", T), sa.Column("date", D), sa.Column("started_at", T), sa.Column("finished_at", T),
        sa.Column("hours", N(6, 2)), sa.Column("hourly_rate", N(8, 2)), sa.Column("amount", N(10, 2)), sa.Column("notes", T),
    )
    op.create_table(
        "dr_staff", *_row(), sa.Column("name", T, nullable=False), sa.Column("role", T), sa.Column("contact", T),
        sa.Column("active", B, nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "dr_channels", *_row(), _fk("apartment_id", "dr_apartments", False),
        sa.Column("channel", T, nullable=False), sa.Column("import_url", T),
        sa.Column("export_token", T, nullable=False, unique=True), sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", T), sa.Column("last_error", T), sa.Column("events", sa.Integer),
        sa.CheckConstraint("channel IN ('airbnb', 'booking', 'other')", name="dr_channels_channel_check"),
    )
    op.create_table(
        "dr_blocks", *_row(), _fk("apartment_id", "dr_apartments", False),
        _fk("channel_id", "dr_channels", ondelete="SET NULL"),
        sa.Column("source", T, nullable=False), sa.Column("start", D, nullable=False), sa.Column("end", D, nullable=False),
        sa.Column("reason", T), sa.Column("summary", T), sa.Column("external_uid", T),
        sa.Column("reserved", B, nullable=False, server_default=sa.text("true")),
        sa.Column("status", T, nullable=False, server_default="active"), sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("source IN ('manual', 'airbnb', 'booking', 'other')", name="dr_blocks_source_check"),
    )
    op.create_index("dr_blocks_apt_idx", "dr_blocks", ["apartment_id", "start"])


def downgrade() -> None:
    for t in TABLES:
        op.drop_table(t)
