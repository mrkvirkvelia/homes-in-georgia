from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db import Base


class SignDoc(Base):
    """«Документ на подпись» (services/sign_docs.py, migration 0029): staff paste a title and a body into our standard
    template (the NDA's layout: header, number + date, parties, the text, signatures); the company's signature (David,
    drawn once for the NDA) goes in when it is sent, each signer gets a link /doc/<token> (the NDA's signing page).
    черновик (draft) → отправлен (sent) → подписан (signed) | отменён (cancelled); a signed document never changes."""
    __tablename__ = "sign_docs"
    __table_args__ = (Index("sign_docs_created_idx", "created_at"),
                      CheckConstraint("status IN ('draft', 'sent', 'signed', 'cancelled')", name="sign_docs_status_check"),
                      CheckConstraint("lang IN ('KA', 'RU', 'KA-RU')", name="sign_docs_lang_check"))
    id = Column(Integer, primary_key=True)
    status = Column(Text, nullable=False, server_default="draft")
    lang = Column(Text, nullable=False)
    title = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))  # {"ka": …, "ru": …}
    body = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))  # the pasted plain text per language
    html = Column(Text, nullable=False, server_default="")
    doc_sha256 = Column(Text, nullable=False, server_default="")
    company_signature = Column(Text)  # data:image/png, put in when sent
    company_signed_at = Column(DateTime(timezone=True))
    pdf_path = Column(Text)
    drive_file_id = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    signed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    signers = relationship("SignDocSigner", order_by="SignDocSigner.id", cascade="all, delete-orphan", lazy="selectin")


class SignDocSigner(Base):
    """One signer of a SignDoc: the other party (a team member or an outside person) or our second signer (staff). The
    tg_* columns are the Telegram confirmation (services/signing.py), required for team members and a named @username."""
    __tablename__ = "sign_doc_signers"
    __table_args__ = (CheckConstraint("side IN ('party', 'company')", name="sign_doc_signers_side_check"),)
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("sign_docs.id", ondelete="CASCADE"), nullable=False, index=True)
    side = Column(Text, nullable=False)  # party = the other party; company = our second signer
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    full_name = Column(Text, nullable=False)
    personal_id = Column(Text)
    phone = Column(Text)
    telegram = Column(Text)  # @username without «@»: only this account may sign
    role = Column(Text)  # «Договор между сторонами»: the signer's label («Собственник», «Клиент»), 0033
    token = Column(Text, nullable=False, unique=True)
    tg_id = Column(Text)
    tg_username = Column(Text)
    tg_name = Column(Text)
    tg_auth_date = Column(DateTime(timezone=True))
    tg_hash = Column(Text)
    signature = Column(Text)
    ip = Column(Text)
    user_agent = Column(Text)
    signed_at = Column(DateTime(timezone=True))
