"""One-off move of ApartFlow (Daily Rent, Node + SQLite) into the CRM's dr_* tables, with checks.

    python -m app.importers.apartflow /path/to/apartflow.db            # check only: everything rolled back
    python -m app.importers.apartflow /path/to/apartflow.db --commit   # write, if every check passes

The SQLite file is opened read-only (copy it from /opt/apartflow/data/apartflow.db, or run on the server). Re-runnable:
rows are matched by legacy_id (ApartFlow's id) and updated in place; audit_log rows already moved are skipped.
Soft-deleted rows come over deleted. Expenses whose stay never existed in ApartFlow (it ignores them in its money too)
keep booking_id empty and the old id in extra.legacy_booking_id. Fields with no column stay in `extra`.

Checks (any mismatch = nothing written): live and deleted counts per table; money per currency (stays' gross, expenses'
amounts); and for every live stay ApartFlow's own formula (calcBk, ported independently over the raw JSON below) against
the CRM's services/daily_rent.calc() at a fixed rate — net, owner and platform shares to the cent."""
import argparse
import json
import sqlite3
import sys
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DrApartment, DrBooking, DrCleaning, DrExpense, DrStaff, Event
from app.services import daily_rent as R

CHECK_RATE = 2.7
ACTOR = "import:apartflow"
ENTITY = {"apartments": "dr_apartment", "bookings": "dr_booking", "expenses": "dr_expense", "cleaning": "dr_cleaning",
          "staff": "dr_staff", "blocks": "dr_block", "channels": "dr_channel"}
# ApartFlow columns the bookings sheet carried but nobody fills (all empty in the data): kept in extra if not empty
BOOKING_COLS = {"apartment_id", "platform", "guest_name", "check_in", "check_out", "gross_income", "income_currency", "tax_pct",
                "booking_fee", "platform_pct", "payment_status", "paid_out", "paid_out_at", "assigned_staff", "comment",
                "apartment_name", "booking_id"}


def num(v):
    """normalize.js toNumber: '' → None; '1,5' → 1.5; unparseable → None (the raw value stays in extra)."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(str(v).strip().replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def day(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def flag(v, default=None):
    if v is True or v is False:
        return v
    s = str(v if v is not None else "").strip().lower()
    return True if s in ("true", "1", "yes") else False if s in ("false", "0", "no") else default


def text(v):
    return None if v is None or v == "" else str(v)


def active(a: dict) -> bool:
    """index.html isActive(): explicit active wins, else status != inactive."""
    f = flag(a.get("active"))
    return f if f is not None else a.get("status") != "inactive"


def read(path: str) -> dict:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for t in ("apartments", "bookings", "expenses", "cleaning", "staff", "blocks", "channels"):
        try:
            out[t] = [{**json.loads(r["data"]), "_id": r["id"], "_created": r["created_at"], "_updated": r["updated_at"],
                       "_deleted": r["deleted_at"]} for r in con.execute(f"SELECT * FROM {t} ORDER BY created_at, id")]
        except sqlite3.OperationalError:
            out[t] = []
    out["audit_log"] = [dict(r) for r in con.execute("SELECT * FROM audit_log ORDER BY id")]
    con.close()
    return out


def _put(db: Session, model, legacy: str, src: dict, values: dict):
    o = db.scalar(select(model).where(model.legacy_id == legacy))
    if o is None:
        o = model(legacy_id=legacy)
        db.add(o)
    for k, v in values.items():
        setattr(o, k, v)
    o.created_at = ts(src["_created"]) or o.created_at
    o.updated_at = ts(src["_updated"]) or o.updated_at
    o.deleted_at = ts(src["_deleted"])
    db.flush()
    return o


def load(db: Session, src: dict) -> dict:
    ids: dict[str, dict[str, int]] = {t: {} for t in ENTITY}
    for a in src["apartments"]:
        legacy_left = {k: a[k] for k in ("owner_percentage", "platform_percentage", "tax", "apartment_id") if a.get(k) not in (None, "")}
        notes = "\n".join(x for x in [text(a.get("notes")), *(f"ApartFlow {k}: {v}" for k, v in legacy_left.items() if k != "apartment_id")] if x)
        plats = [p.strip() for p in str(a.get("platforms") or "Airbnb,Booking").split(",") if p.strip()]
        o = _put(db, DrApartment, a["_id"], a, {
            "name": (a.get("apartment_name") or "").strip() or f"Квартира {a['_id']}", "address": text(a.get("address")),
            "owner_name": text(a.get("owner_name")), "owner_contact": text(a.get("owner_contact")),
            "owner_account": text(a.get("owner_account")), "platform_pct": num(a.get("platform_pct")) or 20,
            "platforms": [p for p in plats if p in ("Airbnb", "Booking", "Другое")] or ["Airbnb", "Booking"],
            "status": a.get("status") if a.get("status") in ("free", "busy", "clean", "tech") else "free",
            "active": active(a), "rooms": int(num(a.get("rooms"))) if num(a.get("rooms")) is not None else None,
            "notes": notes or None, "util_rates": a.get("util_rates") if isinstance(a.get("util_rates"), dict) else {}})
        ids["apartments"][a["_id"]] = o.id
    for b in src["bookings"]:
        plat = b.get("platform") or "Airbnb"
        extra = {k: v for k, v in b.items() if k not in BOOKING_COLS and not k.startswith("_") and v not in ("", None)}
        if num(b.get("gross_income")) is None and b.get("gross_income") not in ("", None):
            extra["gross_income_raw"] = b["gross_income"]
        o = _put(db, DrBooking, b["_id"], b, {
            "apartment_id": ids["apartments"][str(b["apartment_id"])], "platform": plat if plat in ("Airbnb", "Booking", "Другое") else "Другое",
            "guest_name": text(b.get("guest_name")), "check_in": day(b.get("check_in")), "check_out": day(b.get("check_out")),
            "gross": num(b.get("gross_income")),
            # calcBk: a stay without a currency is GEL on Booking, USD elsewhere
            "currency": b.get("income_currency") or ("GEL" if plat == "Booking" else "USD"),
            "tax_pct": num(b.get("tax_pct")) or 0, "booking_fee": num(b.get("booking_fee")),
            "platform_pct": num(b.get("platform_pct")) if num(b.get("platform_pct")) is not None else 20,
            "payment_status": b.get("payment_status") if b.get("payment_status") in ("received", "pending", "partial") else "pending",
            "paid_out": flag(b.get("paid_out"), False), "paid_out_at": day(b.get("paid_out_at")),
            "assigned_staff": text(b.get("assigned_staff")), "comment": text(b.get("comment")),
            "extra": {**extra, **({"platform_raw": plat} if plat not in ("Airbnb", "Booking", "Другое") else {})}})
        ids["bookings"][b["_id"]] = o.id
    for e in src["expenses"]:
        bid = ids["bookings"].get(str(e.get("booking_id") or ""))
        extra = {} if bid or not e.get("booking_id") else {"legacy_booking_id": e["booking_id"]}
        if num(e.get("amount")) is None and e.get("amount") not in ("", None):
            extra["amount_raw"] = e["amount"]
        cat = e.get("category") or e.get("cat") or "other"
        o = _put(db, DrExpense, e["_id"], e, {
            "booking_id": bid, "apartment_id": ids["apartments"].get(str(e.get("apartment_id") or "")),
            "category": cat if cat in R.EXP_LABELS else "other", "amount": num(e.get("amount")),
            "currency": e.get("currency") if e.get("currency") in ("USD", "GEL") else "GEL",
            "payer": "owner" if e.get("payer") == "owner" else "platform", "comment": text(e.get("comment")),
            "date": day(e.get("date")), "created_by": text(e.get("created_by")),
            "extra": {**extra, **({"category_raw": cat} if cat not in R.EXP_LABELS else {})}})
        ids["expenses"][e["_id"]] = o.id
    for c in src["cleaning"]:
        o = _put(db, DrCleaning, c["_id"], c, {
            "apartment_id": ids["apartments"][str(c["apartment_id"])], "cleaner": text(c.get("cleaner")), "date": day(c.get("date")),
            "started_at": text(c.get("started_at")), "finished_at": text(c.get("finished_at")), "hours": num(c.get("total_hours")),
            "hourly_rate": num(c.get("hourly_rate")), "amount": num(c.get("total_amount")), "notes": text(c.get("notes"))})
        ids["cleaning"][c["_id"]] = o.id
    for s in src["staff"]:
        o = _put(db, DrStaff, s["_id"], s, {"name": str(s.get("name") or "—"), "role": text(s.get("role")),
                                             "contact": text(s.get("contact")), "active": flag(s.get("active"), True)})
        ids["staff"][s["_id"]] = o.id
    if src["blocks"] or src["channels"]:
        raise SystemExit("ApartFlow has blocks / channels now: extend the import for them (it had none on 2026-11-15)")
    return ids


def load_audit(db: Session, src: dict, ids: dict) -> int:
    done = {x for (x,) in db.execute(select(Event.data["legacy_audit"].as_integer()).where(Event.data.has_key("legacy_audit")))}
    n = 0
    for r in src["audit_log"]:
        if r["id"] in done or r["entity"] not in ENTITY:
            continue
        db.add(Event(entity=ENTITY[r["entity"]], entity_id=str(ids.get(r["entity"], {}).get(r["entity_id"], r["entity_id"])),
                     action=r["action"], actor_label=r["actor"] or ACTOR, at=ts(r["ts"]),
                     data={"legacy_audit": r["id"], "legacy_id": r["entity_id"],
                           "before": json.loads(r["before"]) if r["before"] else None,
                           "after": json.loads(r["after"]) if r["after"] else None}))
        n += 1
    return n


# ---------------------------------------------------------------- checks

def js_calc(b: dict, expenses: list[dict], rate: float) -> dict:
    """index.html calcBk over ApartFlow's raw JSON — written apart from the import mapping on purpose."""
    def pf(v):  # parseFloat(v) || 0, for the values ApartFlow stores (numbers or '')
        try:
            return float(v) if v not in ("", None) else 0.0
        except (TypeError, ValueError):
            return 0.0
    r = lambda x: round(x + 0.0, 2)  # noqa: E731
    plat = b.get("platform") or "Airbnb"
    cur = b.get("income_currency") or ("GEL" if plat == "Booking" else "USD")
    gross = pf(b.get("gross_income"))
    tax = r(gross * pf(b.get("tax_pct")) / 100)
    fee = pf(b.get("booking_fee")) if plat == "Booking" else 0
    rows = []
    for e in expenses:
        if not e.get("booking_id") or str(e["booking_id"]) != b["_id"]:
            continue
        amt = pf(e.get("amount"))
        if amt <= 0 or amt > 50000:
            continue
        ec = e["currency"] if e.get("currency") in ("USD", "GEL") else "GEL"
        rows.append((amt if ec == cur else (r(amt / rate) if cur == "USD" else r(amt * rate)), e.get("payer")))
    total = r(sum(x for x, _ in rows))
    net = r(r(gross - tax) - total - fee)
    return {"net": net, "platform": r(r(net * 20 / 100) + r(sum(x for x, p in rows if p == "platform")) + fee),
            "owner": r(r(net * 80 / 100) + r(sum(x for x, p in rows if p == "owner")))}


def check(db: Session, src: dict) -> list[str]:
    errs = []
    for t, model in (("apartments", DrApartment), ("bookings", DrBooking), ("expenses", DrExpense), ("cleaning", DrCleaning), ("staff", DrStaff)):
        for live in (True, False):
            want = sum(1 for x in src[t] if (not x["_deleted"]) == live)
            got = db.scalar(select(func.count()).select_from(model).where(model.legacy_id.is_not(None),
                                                                         model.deleted_at.is_(None) if live else model.deleted_at.is_not(None)))
            if want != got:
                errs.append(f"{t} {'live' if live else 'deleted'}: ApartFlow {want}, CRM {got}")
    live_b = [b for b in src["bookings"] if not b["_deleted"]]
    for cur in ("USD", "GEL"):
        want = round(sum(num(b.get("gross_income")) or 0 for b in live_b
                         if (b.get("income_currency") or ("GEL" if b.get("platform") == "Booking" else "USD")) == cur), 2)
        got = round(float(db.scalar(select(func.coalesce(func.sum(DrBooking.gross), 0)).where(DrBooking.deleted_at.is_(None), DrBooking.currency == cur))), 2)
        if want != got:
            errs.append(f"gross {cur}: ApartFlow {want}, CRM {got}")
        want = round(sum(num(e.get("amount")) or 0 for e in src["expenses"] if not e["_deleted"] and (e.get("currency") or "GEL") == cur), 2)
        got = round(float(db.scalar(select(func.coalesce(func.sum(DrExpense.amount), 0)).where(DrExpense.deleted_at.is_(None), DrExpense.currency == cur))), 2)
        if want != got:
            errs.append(f"expenses {cur}: ApartFlow {want}, CRM {got}")
    crm = {b["legacy_id"]: b for b in R.bookings(db, rate=CHECK_RATE)}
    live_e = [e for e in src["expenses"] if not e["_deleted"]]
    totals = {"net": [0.0, 0.0], "owner": [0.0, 0.0], "platform": [0.0, 0.0]}
    for b in live_b:
        want, got = js_calc(b, live_e, CHECK_RATE), crm[b["_id"]]["calc"]
        for k in totals:
            totals[k][0] += want[k]
            totals[k][1] += got[k]
            if want[k] != got[k]:
                errs.append(f"stay {b['_id']} {k}: ApartFlow {want[k]}, CRM {got[k]}")
    paid_want = sum(1 for b in live_b if flag(b.get("paid_out"), False))
    if paid_want != sum(1 for b in crm.values() if b["paid_out"]):
        errs.append("paid out stays differ")
    return errs


def report(db: Session, src: dict) -> dict:
    rows = R.bookings(db, rate=CHECK_RATE)
    e = R.econ(rows)
    return {"apartments": len(src["apartments"]), "bookings_live": len(rows), "expenses": len(src["expenses"]),
            "cleaning": len(src["cleaning"]), "staff": len(src["staff"]), "audit_log": len(src["audit_log"]),
            "gross": e["gross"], "owner": e["owner"], "owner_not_paid": e["to_pay"], "rate_for_check": CHECK_RATE}


def run(db: Session, path: str, commit: bool) -> dict:
    src = read(path)
    ids = load(db, src)
    moved = load_audit(db, src, ids)
    db.flush()
    errs = check(db, src)
    res = {**report(db, src), "audit_moved": moved, "errors": errs, "committed": False}
    if errs or not commit:
        db.rollback()
    else:
        db.commit()
        res["committed"] = True
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sqlite")
    ap.add_argument("--commit", action="store_true", help="write (default: check only, roll back)")
    a = ap.parse_args()
    with SessionLocal() as db:
        res = run(db, a.sqlite, a.commit)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    sys.exit(1 if res["errors"] else 0)


if __name__ == "__main__":
    main()
