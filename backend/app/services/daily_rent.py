"""«Посуточная аренда»: apartments, stays, expenses, cleanings, staff; the money and the owner payouts.

The money is ApartFlow's calcBk (index.html), line for line, so the numbers stay the same after the move:
    tax      = gross × tax_pct            after_tax = gross − tax
    fee      = booking_fee (Booking only)  expenses  = the stay's expenses in its currency (other currency at the NBG rate)
    net      = after_tax − expenses − fee
    platform = net × platform_pct + expenses the platform paid + fee
    owner    = net × (100 − platform_pct) + expenses the owner paid
Everything rounded to 2 decimals at each step, as ApartFlow does. Totals over many stays are in USD (USD→GEL rate of the
National Bank, services/site_feed.rates()), per-currency mixes too. Calendar / iCal: services/daily_rent_ical.py."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DrApartment, DrBlock, DrBooking, DrChannel, DrCleaning, DrExpense, DrStaff, Event, User
from app.services import site_feed
from app.services.common import TZ, get_or_404, log_event, now
from app.services.errors import DomainError

ENTITY = {DrApartment: "dr_apartment", DrBooking: "dr_booking", DrExpense: "dr_expense", DrCleaning: "dr_cleaning",
          DrStaff: "dr_staff", DrChannel: "dr_channel", DrBlock: "dr_block"}
# what a form may write (status-like fields included); ids, photos, legacy_id, deleted_at only through the calls here
FIELDS = {
    DrApartment: ("name", "address", "owner_name", "owner_contact", "owner_account", "platform_pct", "platforms", "status",
                  "active", "rooms", "notes", "util_rates", "price_night", "currency", "description", "district"),
    DrBooking: ("apartment_id", "platform", "guest_name", "check_in", "check_out", "gross", "currency", "tax_pct",
                "booking_fee", "platform_pct", "payment_status", "paid_out", "paid_out_at", "assigned_staff", "comment"),
    DrExpense: ("booking_id", "apartment_id", "category", "amount", "currency", "payer", "comment", "date", "created_by"),
    DrCleaning: ("apartment_id", "cleaner", "date", "started_at", "finished_at", "hours", "hourly_rate", "amount", "notes"),
    DrStaff: ("name", "role", "contact", "active"),
}
EXP_LABELS = {"cleaning": "Уборка", "telmico": "💧 Telmico", "gwp": "🔥 GWP", "energy": "⚡ Tbilisi Energy",
              "internet": "🌐 Internet", "tbilisi_clean": "🗑 Tbilisi Clean", "supplies": "Расходники", "repair": "Ремонт",
              "other": "Прочее"}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
DEFAULT_RATE = 2.7  # ApartFlow's fallback when the bank does not answer


def r2(x) -> float:
    return round(float(x) + 0.0, 2)


def today() -> date:
    return now().astimezone(TZ).date()


def usd_gel() -> float:
    """GEL per 1 USD (the bank's rate, cached by site_feed)."""
    g = site_feed.rates().get("GEL")
    return round(1 / g, 4) if g else DEFAULT_RATE


def _val(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def out(o) -> dict:
    return {c.name: _val(getattr(o, c.name)) for c in o.__table__.columns}


# ---------------------------------------------------------------- money

def calc(b: DrBooking, expenses: list[DrExpense], rate: float) -> dict:
    cur = b.currency
    gross = float(b.gross or 0)
    tax_pct = float(b.tax_pct or 0)
    tax = r2(gross * tax_pct / 100)
    after_tax = r2(gross - tax)
    fee = float(b.booking_fee or 0) if b.platform == "Booking" else 0.0
    exps = []
    for e in expenses:
        amt = float(e.amount or 0)
        if amt <= 0 or amt > 50000:  # ApartFlow skips empty / absurd amounts
            continue
        ecur = e.currency if e.currency in ("USD", "GEL") else "GEL"
        in_b = amt if ecur == cur else (r2(amt / rate) if cur == "USD" else r2(amt * rate))
        exps.append({"id": e.id, "category": e.category, "amount": amt, "currency": ecur, "in_booking": in_b,
                     "payer": e.payer, "comment": e.comment})
    total = r2(sum(x["in_booking"] for x in exps))
    net = r2(after_tax - total - fee)
    p_pct = float(b.platform_pct if b.platform_pct is not None else 20)
    o_pct = 100 - p_pct
    p_base, o_base = r2(net * p_pct / 100), r2(net * o_pct / 100)
    exp_plat = r2(sum(x["in_booking"] for x in exps if x["payer"] == "platform"))
    exp_own = r2(sum(x["in_booking"] for x in exps if x["payer"] == "owner"))
    p_fin, o_fin = r2(p_base + exp_plat + fee), r2(o_base + exp_own)
    usd = (lambda v: v) if cur == "USD" else (lambda v: r2(v / rate))
    return {"currency": cur, "gross": gross, "tax_pct": tax_pct, "tax": tax, "after_tax": after_tax, "booking_fee": fee,
            "expenses": exps, "total_expenses": total, "net": net, "platform_pct": p_pct, "owner_pct": o_pct,
            "platform_base": p_base, "owner_base": o_base, "exp_platform": exp_plat, "exp_owner": exp_own,
            "platform": p_fin, "owner": o_fin, "gross_usd": usd(gross), "net_usd": usd(net), "platform_usd": usd(p_fin),
            "owner_usd": usd(o_fin), "costs_usd": usd(r2(total + tax + fee))}


def nights(b) -> int:
    return max(0, (b.check_out - b.check_in).days) if b.check_in and b.check_out else 0


def _expenses_by_booking(db: Session, ids) -> dict[int, list[DrExpense]]:
    by: dict[int, list[DrExpense]] = {}
    if ids:
        for e in db.scalars(select(DrExpense).where(DrExpense.booking_id.in_(list(ids)), DrExpense.deleted_at.is_(None))
                            .order_by(DrExpense.id)):
            by.setdefault(e.booking_id, []).append(e)
    return by


def booking_out(b: DrBooking, exps: list[DrExpense], rate: float) -> dict:
    return {**out(b), "nights": nights(b), "calc": calc(b, exps, rate), "expenses": [out(e) for e in exps]}


def bookings(db: Session, apartment_id: int | None = None, month_from: str | None = None, month_to: str | None = None,
             rate: float | None = None) -> list[dict]:
    """Live stays (newest check-in first) with their money; month_from / month_to 'YYYY-MM' filter by check-in month."""
    rate = rate or usd_gel()
    stmt = select(DrBooking).where(DrBooking.deleted_at.is_(None)).order_by(DrBooking.check_in.desc().nullslast(), DrBooking.id.desc())
    if apartment_id:
        stmt = stmt.where(DrBooking.apartment_id == apartment_id)
    if month_from:
        stmt = stmt.where(DrBooking.check_in >= date.fromisoformat(month_from + "-01"))
    if month_to:
        y, m = map(int, month_to.split("-"))
        stmt = stmt.where(DrBooking.check_in < date(y + m // 12, m % 12 + 1, 1))
    rows = list(db.scalars(stmt))
    by = _expenses_by_booking(db, [b.id for b in rows])
    return [booking_out(b, by.get(b.id, []), rate) for b in rows]


def _mix(acc: dict, cur: str, v: float):
    if not v:
        return
    acc[cur] = r2(acc.get(cur, 0) + v)


def econ(rows: list[dict], days: int | None = None) -> dict:
    """ApartFlow's econ(): the KPIs of a set of stays (rows from bookings())."""
    e = {"stays": 0, "nights": 0, "gross_usd": 0.0, "net_usd": 0.0, "platform_usd": 0.0, "owner_usd": 0.0, "to_pay_usd": 0.0,
         "costs_usd": 0.0, "gross": {}, "owner": {}, "to_pay": {}}
    for b in rows:
        c = b["calc"]
        e["stays"] += 1
        e["nights"] += b["nights"]
        for k in ("gross_usd", "net_usd", "platform_usd", "owner_usd", "costs_usd"):
            e[k] += c[k]
        _mix(e["gross"], c["currency"], c["gross"])
        _mix(e["owner"], c["currency"], c["owner"])
        if not b["paid_out"]:
            e["to_pay_usd"] += c["owner_usd"]
            _mix(e["to_pay"], c["currency"], c["owner"])
    for k in ("gross_usd", "net_usd", "platform_usd", "owner_usd", "costs_usd", "to_pay_usd"):
        e[k] = r2(e[k])
    e["adr_usd"] = r2(e["gross_usd"] / e["nights"]) if e["nights"] else 0
    e["occupancy"] = min(100, round(e["nights"] / days * 100)) if days else None
    return e


def month_days(month_from: str | None, month_to: str | None) -> int | None:
    if not month_from or not month_to:
        return None
    a = date.fromisoformat(month_from + "-01")
    y, m = map(int, month_to.split("-"))
    return (date(y + m // 12, m % 12 + 1, 1) - a).days


def summary(db: Session, month_from: str | None, month_to: str | None) -> dict:
    """The dashboard: totals and per apartment for the period, monthly income for the chart, the payouts due."""
    rate = usd_gel()
    rows = bookings(db, None, month_from, month_to, rate)
    days = month_days(month_from, month_to)
    apts = list(db.scalars(select(DrApartment).where(DrApartment.deleted_at.is_(None)).order_by(DrApartment.id)))
    per = []
    for a in apts:
        mine = [b for b in rows if b["apartment_id"] == a.id]
        if mine or a.active:
            per.append({"apartment": out(a), "econ": econ(mine, days)})
    months: dict[str, float] = {}
    for b in rows:
        if b["check_in"]:
            months[b["check_in"][:7]] = r2(months.get(b["check_in"][:7], 0) + b["calc"]["gross_usd"])
    return {"rate": rate, "total": econ(rows, days * len([a for a in apts if a.active]) if days else None),
            "apartments": per, "months": dict(sorted(months.items())), "payouts": payouts(db, rate)}


def _ready(b: dict) -> bool:
    """The owner's share can be paid: the money came in (not «Ожидается») and there is something to pay."""
    return not b["paid_out"] and b["payment_status"] != "pending" and b["calc"]["owner"] > 0


def payouts(db: Session, rate: float | None = None) -> list[dict]:
    """Per apartment: stays not yet paid to the owner. ready = the money came in, so it can be paid now."""
    rate = rate or usd_gel()
    rows = [b for b in bookings(db, rate=rate) if not b["paid_out"] and b["calc"]["owner"] > 0]
    res = []
    for a in db.scalars(select(DrApartment).where(DrApartment.deleted_at.is_(None)).order_by(DrApartment.id)):
        mine = [b for b in rows if b["apartment_id"] == a.id]
        if not mine:
            continue
        ready, wait = {}, {}
        for b in mine:
            _mix(ready if _ready(b) else wait, b["calc"]["currency"], b["calc"]["owner"])
        res.append({"apartment": out(a), "bookings": sorted(mine, key=lambda b: b["check_in"] or ""), "ready": ready,
                    "waiting": wait, "ready_count": sum(1 for b in mine if _ready(b))})
    return res


def pay(db: Session, booking_ids: list[int] | None, apartment_id: int | None, paid: bool, actor: User) -> dict:
    """Mark stays paid out to the owner (today) — one, or all ready ones of an apartment — or undo one (paid=False)."""
    rate = usd_gel()
    if apartment_id and not booking_ids:
        booking_ids = [b["id"] for b in bookings(db, apartment_id, rate=rate) if _ready(b)]
    done = 0
    for bid in booking_ids or []:
        b = get_or_404(db, DrBooking, bid, "booking", lock=True)
        if b.deleted_at or b.paid_out == paid:
            continue
        update(db, DrBooking, bid, {"paid_out": paid, "paid_out_at": today() if paid else None}, actor, commit=False)
        done += 1
    db.commit()
    return {"changed": done}


# ---------------------------------------------------------------- reports (texts to copy / send to the owner)

def _day(d: str | None) -> str:
    if not d:
        return "—"
    x = date.fromisoformat(d[:10])
    return f"{x.day:02d} {MONTHS[x.month - 1]}"


def _short(d: str | None) -> str:
    return date.fromisoformat(d[:10]).strftime("%d.%m.%y") if d else "—"


def nights_label(n: int) -> str:
    return "1 ночь" if n == 1 else f"{n} ночи" if 2 <= n <= 4 else f"{n} ночей"


def money_str(cur: str, v: float) -> str:
    s = f"{v:,.2f}".replace(",", " ").replace(".00", "").replace(".", ",")
    return ("₾" if cur == "GEL" else "$") + s


def mix_str(m: dict) -> str:
    return " + ".join(money_str(c, m[c]) for c in ("USD", "GEL") if m.get(c)) or "—"


def booking_report(a: DrApartment | None, b: dict) -> str:
    """ApartFlow's makeReport (ru): the stay's money for the owner."""
    c = b["calc"]
    S = lambda v: money_str(c["currency"], v)  # noqa: E731
    lines = ["🏠 " + (a.name if a else "—")]
    if a and a.address:
        lines.append("📍 " + a.address + ", Tbilisi")
    lines += ["", f"📅 Период: {_day(b['check_in'])} — {_day(b['check_out'])} ({nights_label(b['nights'])})"]
    if b["guest_name"]:
        lines.append("👤 Гость: " + b["guest_name"])
    lines += ["📱 Платформа: " + b["platform"], "", "💰 Пришло: " + S(c["gross"])]
    if c["tax"] > 0:
        lines.append(f"📉 Налог ({c['tax_pct']:g}%): -" + S(c["tax"]))
    if c["booking_fee"] > 0:
        lines.append("📉 Booking fee: -" + S(c["booking_fee"]))
    if c["total_expenses"] > 0:
        lines.append("🔧 Расходы: -" + S(c["total_expenses"]))
    for e in c["expenses"]:
        who = " [Собственник]" if e["payer"] == "owner" else " [Платформа]"
        lines.append(f"   • {EXP_LABELS.get(e['category'], e['category'])}: {money_str(e['currency'], e['amount'])}{who}"
                     + (f" ({e['comment']})" if e["comment"] else ""))
    lines += ["", "✅ Чистая прибыль: " + S(c["net"]), "",
              f"👤 Платформа ({c['platform_pct']:g}%):", f"   {S(c['net'])} × {c['platform_pct']:g}% = {S(c['platform_base'])}"]
    if c["exp_platform"] > 0:
        lines.append("   + компенсация расходов (Платформа): " + S(c["exp_platform"]))
    if c["booking_fee"] > 0:
        lines.append("   + Booking fee: " + S(c["booking_fee"]))
    lines += ["   = " + S(c["platform"]), "", f"🏦 {(a and a.owner_name) or 'Владелец'} ({c['owner_pct']:g}%):",
              f"   {S(c['net'])} × {c['owner_pct']:g}% = {S(c['owner_base'])}"]
    if c["exp_owner"] > 0:
        lines.append("   + компенсация расходов (Собственник): " + S(c["exp_owner"]))
    lines.append("   = " + S(c["owner"]))
    if a and a.owner_account:
        lines.append("\n🏦 Счёт: " + a.owner_account)
    if b["comment"]:
        lines.append("\n💬 " + b["comment"])
    return "\n".join(lines)


def period_report(a: DrApartment, rows: list[dict], label: str) -> str:
    """ApartFlow's periodReport: every stay of the period and the owner's total."""
    lines = ["🏠 " + a.name, "📅 Период: " + label, ""]
    for b in sorted(rows, key=lambda x: x["check_in"] or ""):
        c = b["calc"]
        lines.append(f"• {_short(b['check_in'])} — {_short(b['check_out'])} ({nights_label(b['nights'])})"
                     + (", " + b["guest_name"] if b["guest_name"] else "") + ", " + b["platform"])
        lines.append(f"   пришло {money_str(c['currency'], c['gross'])} · чистая {money_str(c['currency'], c['net'])} · "
                     f"владельцу {money_str(c['currency'], c['owner'])}" + (" ✓ выплачено" if b["paid_out"] else ""))
    e = econ(rows)
    lines += ["", f"Проживаний: {e['stays']} · ночей: {e['nights']}", "💰 Пришло: " + mix_str(e["gross"]),
              f"🏦 {a.owner_name or 'Владелец'} ({100 - float(a.platform_pct):g}% + компенсации): " + mix_str(e["owner"])]
    if e["to_pay"]:
        lines.append("⏳ Ещё не выплачено: " + mix_str(e["to_pay"]))
    if a.owner_account:
        lines += ["", "🏦 Счёт: " + a.owner_account]
    return "\n".join(lines)


# ---------------------------------------------------------------- writes (every one audited: events dr_<table>)

def _check(model, data: dict, o=None):
    if model is not DrBooking:
        return
    ci = data.get("check_in", o.check_in if o else None)
    co = data.get("check_out", o.check_out if o else None)
    if ci and co and co < ci:
        raise DomainError("bad_dates", "Выезд раньше заезда", 422)
    if data.get("platform", o.platform if o else None) != "Booking" and ("booking_fee" in data or "platform" in data):
        data["booking_fee"] = None  # the fee is Booking's only


def _changes(before: dict, after: dict) -> dict:
    return {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}


def create(db: Session, model, data: dict, actor: User | None, commit: bool = True, label: str | None = None):
    data = {k: v for k, v in data.items() if k in FIELDS[model]}
    _live_refs(db, data)
    _check(model, data)
    o = model(**data)
    db.add(o)
    db.flush()
    log_event(db, ENTITY[model], o.id, "create", actor, label=label, after={k: _val(v) for k, v in data.items()})
    if commit:
        db.commit()
    return o


def update(db: Session, model, oid: int, data: dict, actor: User | None, commit: bool = True, label: str | None = None):
    o = get_or_404(db, model, oid, ENTITY[model][3:], lock=True)
    if o.deleted_at:
        raise DomainError("not_found", "Запись удалена", 404)
    data = {k: v for k, v in data.items() if k in FIELDS[model]}
    _live_refs(db, data)
    _check(model, data, o)
    before = out(o)
    for k, v in data.items():
        setattr(o, k, v)
    db.flush()
    ch = _changes(before, {k: _val(getattr(o, k)) for k in data})
    if ch:
        log_event(db, ENTITY[model], o.id, "update", actor, label=label, changes=ch)
    if commit:
        db.commit()
    return o


def delete(db: Session, model, oid: int, actor: User | None) -> dict:
    """Soft delete; a stay takes its expenses with it (ApartFlow's deleteBooking). An apartment with stays: refused."""
    o = get_or_404(db, model, oid, ENTITY[model][3:], lock=True)
    if o.deleted_at:
        return {"deleted": None}
    if model is DrApartment and db.scalar(select(DrBooking.id).where(DrBooking.apartment_id == oid, DrBooking.deleted_at.is_(None)).limit(1)):
        raise DomainError("has_bookings", "У квартиры есть проживания — сделайте её неактивной вместо удаления", 409)
    o.deleted_at = now()
    log_event(db, ENTITY[model], o.id, "delete", actor, before=out(o))
    n = 0
    if model is DrBooking:
        for e in db.scalars(select(DrExpense).where(DrExpense.booking_id == oid, DrExpense.deleted_at.is_(None))):
            e.deleted_at = now()
            log_event(db, "dr_expense", e.id, "delete", actor, before=out(e))
            n += 1
    db.commit()
    return {"deleted": oid, "expenses_deleted": n}


def _live_refs(db: Session, data: dict):
    for k, model, what in (("apartment_id", DrApartment, "Квартира"), ("booking_id", DrBooking, "Проживание")):
        if data.get(k) is not None:
            x = db.get(model, data[k])
            if not x or x.deleted_at:
                raise DomainError("not_found", f"{what} не найдена" if what == "Квартира" else f"{what} не найдено", 404)


def new_booking_defaults(a: DrApartment, platform: str | None = None) -> dict:
    """ApartFlow's initBKF: the first platform of the apartment; Airbnb → USD and 1% tax, the rest GEL and 0%."""
    p = platform or ((a.platforms or ["Airbnb"])[0])
    return {"platform": p, "currency": "USD" if p == "Airbnb" else "GEL", "tax_pct": 1 if p == "Airbnb" else 0,
            "platform_pct": float(a.platform_pct), "payment_status": "received"}


def create_booking(db: Session, data: dict, actor: User) -> DrBooking:
    a = db.get(DrApartment, data.get("apartment_id") or 0)
    if not a or a.deleted_at:
        raise DomainError("not_found", "Квартира не найдена", 404)
    return create(db, DrBooking, {**new_booking_defaults(a, data.get("platform")), **data}, actor)


def journal(db: Session, limit: int, offset: int) -> dict:
    """ApartFlow's audit_log: every change in «Посуточная аренда», newest first."""
    where = Event.entity.like("dr\\_%")
    rows = list(db.scalars(select(Event).where(where).order_by(Event.at.desc(), Event.id.desc()).limit(limit).offset(offset)))
    return {"items": [{"id": e.id, "entity": e.entity, "entity_id": e.entity_id, "action": e.action, "actor": e.actor_label,
                       "data": e.data, "at": e.at.isoformat()} for e in rows],
            "total": db.scalar(select(func.count()).select_from(Event).where(where))}
