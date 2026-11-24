"""«Декларации RS.ge» (Irakli 11-24): every field employee with an ИП (users.ie_number) files his own monthly
small-business declaration on rs.ge. rs.ge has no API for declarations, so the CRM does not send anything there: the
agent types the month's turnover in GEL from his bank statement (the CRM's deals are not used), sees the 1 % tax, files
on eservices.rs.ge and marks «Подал». Telegram reminds him on the 1st, 10th and 14th until he has marked it.

A month's declaration is due between the 1st and the DEADLINE_DAY of the next month."""
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FIELD_SQL, Job, TaxDeclaration, User
from app.services import jobs
from app.services.common import TZ, now
from app.services.errors import DomainError, forbidden

RATE = Decimal("0.01")  # small business status: 1 % of the turnover
DEADLINE_DAY = 15
REMIND_DAYS = (1, 10, 14)
HOUR = 10  # the reminders, Tbilisi time
HISTORY = 12  # months shown in the cabinet
RS_URL = "https://eservices.rs.ge"
MAX_TURNOVER = Decimal("1000000000")


def today() -> date:
    return now().astimezone(TZ).date()


def month_start(d: date) -> date:
    return d.replace(day=1)


def prev_month(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def due_period(day: date | None = None) -> date:
    """The month whose declaration is due now: always the previous one."""
    return prev_month(day or today())


def deadline(period: date) -> date:
    nxt = (period.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt.replace(day=DEADLINE_DAY)


def key(period: date) -> str:
    return period.strftime("%Y-%m")


def parse_period(s: str) -> date:
    """«2026-10» → 2026-10-01; only finished months, not older than two years."""
    try:
        y, m = (int(x) for x in s.split("-"))
        p = date(y, m, 1)
    except (ValueError, TypeError):
        raise DomainError("bad_period", "period must be YYYY-MM")
    t = today()
    if p >= month_start(t):
        raise DomainError("bad_period", "the month is not over yet")
    if p < date(t.year - 2, t.month, 1):
        raise DomainError("bad_period", "too old")
    return p


def tax_of(turnover) -> Decimal:
    return (Decimal(turnover) * RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def status(d: TaxDeclaration | None) -> str:
    """missing: nothing typed; entered: the sum is in, not filed yet; filed: he marked it filed on rs.ge."""
    return "missing" if d is None else "filed" if d.filed_at else "entered"


def out(period: date, d: TaxDeclaration | None, day: date | None = None) -> dict:
    day = day or today()
    st = status(d)
    dl = deadline(period)
    # «Просрочена» only for the month due now: older months without a record are before the agent used this page
    return {"period": key(period), "deadline": dl.isoformat(), "status": st,
            "overdue": st != "filed" and day > dl and period == due_period(day), "days_left": (dl - day).days,
            "turnover": float(d.turnover) if d else None, "tax": float(tax_of(d.turnover)) if d else None,
            "filed_at": d.filed_at.isoformat() if d and d.filed_at else None, "note": d.note if d else None,
            "updated_at": d.updated_at.isoformat() if d and d.updated_at else None}


def _by_period(db: Session, uid: int, periods: list[date]) -> dict[date, TaxDeclaration]:
    rows = db.scalars(select(TaxDeclaration).where(TaxDeclaration.user_id == uid, TaxDeclaration.period.in_(periods)))
    return {r.period: r for r in rows}


def mine(db: Session, u: User) -> dict:
    """The cabinet block: the declaration due now and the last HISTORY months, newest first."""
    day = today()
    periods = [due_period(day)]
    for _ in range(HISTORY - 1):
        periods.append(prev_month(periods[-1]))
    have = _by_period(db, u.id, periods)
    return {"has_ie": bool(u.ie_number), "rate": float(RATE), "rs_url": RS_URL, "deadline_day": DEADLINE_DAY,
            "current": out(periods[0], have.get(periods[0]), day),
            "history": [out(p, have.get(p), day) for p in periods]}


def save(db: Session, actor: User, period: str, turnover, filed: bool, note: str | None) -> dict:
    """The agent's own declaration only: staff see the others' but never type for them."""
    if not actor.ie_number:
        raise DomainError("no_ie", "fill in your ИП number in the profile first")
    p = parse_period(period)
    try:
        amount = Decimal(str(turnover)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:  # noqa: BLE001
        raise DomainError("bad_turnover", "turnover must be a number")
    if amount < 0 or amount >= MAX_TURNOVER:
        raise DomainError("bad_turnover", "turnover must be 0 or more")
    d = db.scalar(select(TaxDeclaration).where(TaxDeclaration.user_id == actor.id, TaxDeclaration.period == p)
                  .with_for_update())
    if d is None:
        d = TaxDeclaration(user_id=actor.id, period=p, turnover=amount)
        db.add(d)
    d.turnover = amount
    d.note = (note or "").strip() or None
    d.filed_at = (d.filed_at or now()) if filed else None
    db.commit()
    db.refresh(d)
    return out(p, d)


def view(db: Session, actor: User, user_id: int | None) -> dict:
    from app.models import at_least
    from app.services.common import get_or_404
    if user_id and user_id != actor.id and not at_least(actor, "operator"):
        raise forbidden()
    return mine(db, get_or_404(db, User, user_id, "user") if user_id else actor)


def people(db: Session):
    """Who files: active field employees (agents, recruits, staff «+ как агент»)."""
    return db.scalars(select(User).where(FIELD_SQL, User.is_active.is_(True), User.deleted_at.is_(None))
                      .order_by(User.name))


def overview(db: Session, period: str | None = None) -> dict:
    """Staff: one month's state across the team; people without an ИП number are listed apart (has_ie false)."""
    day = today()
    p = parse_period(period) if period else due_period(day)
    team = list(people(db))
    have = {r.user_id: r for r in db.scalars(select(TaxDeclaration).where(
        TaxDeclaration.period == p, TaxDeclaration.user_id.in_([u.id for u in team] or [0])))}
    rows = [{"user": {"id": u.id, "name": u.name, "photo_url": u.photo_url}, "has_ie": bool(u.ie_number),
             **out(p, have.get(u.id), day)} for u in team]
    with_ie = [r for r in rows if r["has_ie"]]
    return {"period": key(p), "deadline": deadline(p).isoformat(), "rows": rows,
            "totals": {"people": len(with_ie), "filed": sum(r["status"] == "filed" for r in with_ie),
                       "entered": sum(r["status"] == "entered" for r in with_ie),
                       "missing": sum(r["status"] == "missing" for r in with_ie),
                       "no_ie": len(rows) - len(with_ie)}}


# --- Telegram reminders ---------------------------------------------------------------------------------------------

def next_reminder(moment: datetime | None = None) -> date:
    """The next REMIND_DAYS day at HOUR:00 Tbilisi, today included while it is before HOUR."""
    local = (moment or now()).astimezone(TZ)
    d = local.date() if local.hour < HOUR else local.date() + timedelta(days=1)
    while d.day not in REMIND_DAYS:
        d += timedelta(days=1)
    return d


def ensure_job(db: Session) -> None:
    """Keep the next «tax_reminder» job scheduled (ref = its date); a day already handled isn't redone."""
    d = next_reminder()
    if not db.scalar(select(Job.id).where(Job.kind == "tax_reminder", Job.ref == d.isoformat())):
        jobs.schedule(db, "tax_reminder", d.isoformat(), datetime.combine(d, time(HOUR), TZ), replace=False)
        db.commit()


def to_remind(db: Session, day: date) -> list[tuple[User, dict]]:
    """People with an ИП and Telegram whose declaration for the due month is not marked filed."""
    p = due_period(day)
    team = [u for u in people(db) if u.ie_number and u.tg_id]
    have = {r.user_id: r for r in db.scalars(select(TaxDeclaration).where(
        TaxDeclaration.period == p, TaxDeclaration.user_id.in_([u.id for u in team] or [0])))}
    return [(u, out(p, have.get(u.id), day)) for u in team if status(have.get(u.id)) != "filed"]
