"""sign_docs + sign_doc_signers: «Документ на подпись» — any document pasted into our standard template and signed through
the NDA's signing page (David 11-17: «разные договора отправить на подпись»; Stanislav: один шаблон, текст вставляем).

Revision ID: 0029
Revises: 0028
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "sign_docs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("lang", sa.Text, nullable=False),
        sa.Column("title", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("body", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("html", sa.Text, nullable=False, server_default=""),
        sa.Column("doc_sha256", sa.Text, nullable=False, server_default=""),
        sa.Column("company_signature", sa.Text),
        sa.Column("company_signed_at", TZ),
        sa.Column("pdf_path", sa.Text),
        sa.Column("drive_file_id", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", TZ),
        sa.Column("signed_at", TZ),
        sa.Column("cancelled_at", TZ),
        sa.CheckConstraint("status IN ('draft', 'sent', 'signed', 'cancelled')", name="sign_docs_status_check"),
        sa.CheckConstraint("lang IN ('KA', 'RU', 'KA-RU')", name="sign_docs_lang_check"),
    )
    op.create_index("sign_docs_created_idx", "sign_docs", ["created_at"])
    op.create_table(
        "sign_doc_signers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("doc_id", sa.Integer, sa.ForeignKey("sign_docs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("personal_id", sa.Text),
        sa.Column("phone", sa.Text),
        sa.Column("telegram", sa.Text),
        sa.Column("token", sa.Text, nullable=False, unique=True),
        sa.Column("tg_id", sa.Text),
        sa.Column("tg_username", sa.Text),
        sa.Column("tg_name", sa.Text),
        sa.Column("tg_auth_date", TZ),
        sa.Column("tg_hash", sa.Text),
        sa.Column("signature", sa.Text),
        sa.Column("ip", sa.Text),
        sa.Column("user_agent", sa.Text),
        sa.Column("signed_at", TZ),
        sa.CheckConstraint("side IN ('party', 'company')", name="sign_doc_signers_side_check"),
    )
    op.create_index("ix_sign_doc_signers_doc_id", "sign_doc_signers", ["doc_id"])


def downgrade() -> None:
    op.drop_table("sign_doc_signers")
    op.drop_index("sign_docs_created_idx", "sign_docs")
    op.drop_table("sign_docs")
