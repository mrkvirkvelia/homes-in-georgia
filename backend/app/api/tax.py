"""«Декларации RS.ge» (services/tax.py): the agent's monthly turnover and whether he filed it; the team view for staff."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_level
from app.db import get_db
from app.models import User
from app.services import tax

router = APIRouter(tags=["tax"])


class TaxIn(BaseModel):
    turnover: float = Field(ge=0)
    filed: bool = False
    note: str | None = Field(None, max_length=500)


@router.get("/me/tax")
def my_tax(user_id: int | None = None, db: Session = Depends(get_db, scope="function"), user: User = Depends(current_user)):
    """One's own declarations; staff open any employee's with ?user_id= (read-only)."""
    return tax.view(db, user, user_id)


@router.put("/me/tax/{period}")
def save_tax(period: str, body: TaxIn, db: Session = Depends(get_db, scope="function"), user: User = Depends(current_user)):
    return tax.save(db, user, period, body.turnover, body.filed, body.note)


@router.get("/tax/overview")
def tax_overview(period: str | None = None, db: Session = Depends(get_db, scope="function"),
                 user: User = Depends(require_level("operator"))):
    return tax.overview(db, period)
