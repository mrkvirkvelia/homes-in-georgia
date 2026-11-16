"""Catch-up from the old «9010_bot» sheet after the 10.11 import: only the rows it got since, through sheets_csv.

    python -m app.importers.sheets_delta FOLDER            # prints the counts
    python -m app.importers.sheets_delta FOLDER --commit   # same, and keeps it

FOLDER holds CSVs of the NEW rows only (the diff against the 10.11 snapshot is made outside, see the PR / notes).
Differences from a plain sheets_csv run:
  - no people: users, roles and active flags stay as the CRM has them; only Agent_Counters' exclusive_deals grows
    (never down: a counter the CRM already has higher stays);
  - channel posts are insert-only: a post the CRM already tracks keeps its status / agent;
  - no reminders: the old bot still runs T14 for its own deals.
Deals, T0, Photo_Queue, News, Owner_Base keep sheets_csv's keys and twin merge, so a re-run duplicates nothing."""
import csv
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.importers.sheets_csv import Importer, integer, read
from app.models import ChannelPost


def run(folder: Path, db) -> dict:
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
    return {k: dict(v) | ({"errors": imp.errors[k]} if imp.errors.get(k) else {}) for k, v in imp.stats.items()}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    db = SessionLocal()
    if "--commit" not in argv:  # Importer.each commits per sheet: a dry run must not reach it
        db.commit = db.flush
    stats = run(Path(argv[0]), db)
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
