"""Catch-up from the old «9010_bot» sheet after the 10.11 import: only the rows it got since, through sheets_csv.

    python -m app.importers.sheets_delta FOLDER            # prints the counts
    python -m app.importers.sheets_delta FOLDER --commit   # same, and keeps it

FOLDER holds CSVs of the NEW rows only (the diff against the 10.11 snapshot is made outside, see the PR / notes).
Differences from a plain sheets_csv run:
  - no people: users, roles and active flags stay as the CRM has them; only Agent_Counters' exclusive_deals grows
    (never down: a counter the CRM already has higher stays);
  - channel posts are insert-only: a post the CRM already tracks keeps its status / agent;
  - no reminders: the old bot still runs T14 for its own deals.
Deals, T0, Photo_Queue, News, Owner_Base keep sheets_csv's keys and twin merge, so a re-run duplicates nothing.

FOLDER/_phones.json (optional): the numbers behind «#ERROR!» cells — the old bot wrote «+995 5xx …», Sheets took it
for a formula, so the 10.11 import stored «#ERROR!». A field is set only while it still holds «#ERROR!».
`--phones-only` applies just these."""
import csv
import json
import sys
from collections import Counter, defaultdict
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.importers.sheets_csv import Importer, integer, read
from app.models import ChannelPost, Deal, Owner, Report
from app.services.dedup import norm_phone

ERR = "#ERROR"


def phones(db, fixes: list) -> dict:
    n = Counter()
    for f in fixes:
        if f["kind"] == "deal":
            d = db.scalar(select(Deal).where((Deal.raw["_import_key"].astext == f["key"]) |
                                             Deal.raw["_merged"].contains([f["key"]])).order_by(Deal.id).limit(1))
            if d is None:
                n["deal_not_found"] += 1
            elif ERR in (getattr(d, f["field"]) or ""):
                setattr(d, f["field"], f["phone"])
                n[f"deal_{f['field']}_fixed"] += 1
            else:
                n["deal_already_ok"] += 1
        elif f["kind"] == "report":
            r = db.scalar(select(Report).where(Report.data["_import_key"].astext == f["key"]))
            if r is None:
                n["report_not_found"] += 1
            elif ERR in str((r.data or {}).get(f["field"]) or ""):
                r.data = {**r.data, f["field"]: f["phone"]}
                n["report_fixed"] += 1
            else:
                n["report_already_ok"] += 1
    # owners carry no import key: the same address + name among owners still on «#ERROR!»; one number per group
    groups = defaultdict(set)
    for f in fixes:
        if f["kind"] == "owner":
            groups[(f["address_norm"], f["name"])].add(f["phone"])
    for (an, name), ph in groups.items():
        rows = list(db.scalars(select(Owner).where(Owner.phone.contains(ERR), Owner.address_norm == an,
                                                   Owner.name.is_not_distinct_from(name))))
        if not rows:
            n["owner_not_found_or_ok"] += 1
        elif len(ph) > 1:
            n["owner_conflict_several_numbers"] += 1  # same address + name, different numbers: left for a person
        else:
            for o in rows:
                o.phone, o.phone_norm = next(iter(ph)), norm_phone(next(iter(ph)))
                n["owner_fixed"] += 1
    db.commit()
    return dict(n)


def run(folder: Path, db, phones_only=False) -> dict:
    fixes = json.loads((folder / "_phones.json").read_text()) if (folder / "_phones.json").exists() else []
    if phones_only:
        return {"_phones": phones(db, fixes)}
    tmp = Path(tempfile.mkdtemp())
    have = set(db.scalars(select(ChannelPost.message_id)))
    for p in folder.glob("*.csv"):
        h, rows = read(p)
        if p.stem in ("Listings", "Active_Listings"):
            rows = [r for r in rows if r and r[0].strip() not in have]
        with (tmp / p.name).open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([h, *rows] if h else [])
    imp = Importer(db, tmp)
    imp.owners()
    imp.deals()
    imp.evaluations()
    imp.reports()
    imp.content()

    def counters(r, rec):
        u, n = imp.user_by_name(rec.get("agent")), integer(rec.get("exclusive_deals"))
        if not u or n is None:
            return "unmatched"
        if (u.exclusive_deals or 0) >= n:
            return "unchanged"
        u.exclusive_deals = n
        return "updated"
    imp.each("Agent_Counters", counters)
    if fixes:
        imp.stats["_phones"] = phones(db, fixes)
    return {k: dict(v) | ({"errors": imp.errors[k]} if imp.errors.get(k) else {}) for k, v in imp.stats.items()}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    db = SessionLocal()
    if "--commit" not in argv:  # Importer.each commits per sheet: a dry run must not reach it
        db.commit = db.flush
    stats = run(Path(argv[0]), db, phones_only="--phones-only" in argv)
    for sheet, st in stats.items():
        print(f"  {sheet:20s} " + ", ".join(f"{k}={v}" for k, v in sorted(st.items())))
    if "--commit" in argv:
        db.commit()
        print("committed")
    else:
        db.rollback()
        print("dry run: rolled back (add --commit)")


if __name__ == "__main__":
    main()
