from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class TaxDeclaration(Base):
    """«Декларации RS.ge» (Irakli 11-24, services/tax.py, migration 0039): a field employee with an ИП (users.ie_number)
    files his monthly small-business declaration on rs.ge himself. The CRM only keeps what he typed: the month's turnover
    from his bank statement (not the CRM's deals) and whether he has filed it, and reminds him in Telegram."""
    __tablename__ = "tax_declarations"
    __table_args__ = (Index("tax_declarations_period_idx", "period"),
                      UniqueConstraint("user_id", "period", name="tax_declarations_user_period_key"),
                      CheckConstraint("turnover >= 0", name="tax_declarations_turnover_check"),
                      CheckConstraint("extract(day from period) = 1", name="tax_declarations_period_check"))

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period = Column(Date, nullable=False)  # the first day of the reported month
    turnover = Column(Numeric(14, 2), nullable=False)  # GEL, as the agent read it in his bank statement
    filed_at = Column(DateTime(timezone=True))  # he pressed «Подал на rs.ge»; null = not filed yet
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
