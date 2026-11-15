"""Test data builder for tests/test_site_feed.py: the mapping of the one-off hge.ge import (run on prod 14.11.2026, then
removed from the app; history: commit 5cf93f9). Turns old-site items into CRM rows."""
import argparse
import json
import logging
import os
import re
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.db import SessionLocal
from app.models import Car, ChannelPost, Property, PropertyMedia, PropertyPublication, SaleObject
from app.services import properties as P
from app.services import site_feed as F
from app.services.common import log_event

SOURCE, PHOTO_BASE, UA = "https://hge.ge/data/listings.json", "https://hge.ge/", {"User-Agent": "HomesInGeorgiaImport/1.0"}
MAX_PHOTOS, MAX_BYTES = P.MAX_MEDIA["photo"], 15 * 1024 * 1024
MONTHS = {1, 2, 3, 4, 5, 6, 9, 12}  # the generator's periods; longer ones (24, 36, 60) live in post_fields.months only
log = logging.getLogger("oneoff_import_hge")


def target(it: dict) -> str:
    if it["service"].startswith("car"):
        return "car"
    if it["service"] in ("sale", "new") or it.get("deal") == "sale":
        return "sale"
    return "rent"


def rent_fields(it: dict) -> dict:
    """The site item's facts as post_fields: the generator's CRM tags where they exist, the rest under site_extra."""
    pf, extra = {"service": it["service"], "site_id": it["id"]}, {}
    if it.get("kind") in F.KIND:
        pf["prop_type"] = F.KIND[it["kind"]]
    for key, tbl in (("building", F.BUILDING), ("heating", F.HEATING), ("pets", F.PETS), ("metro", F.METRO)):
        if v := it.get(key):
            if v in tbl:
                pf[key] = tbl[v]
            else:
                extra[key] = v
    c = it.get("condition")
    if c in F.FRAME:
        pf["condition"] = F.FRAME[c]
    elif c in F.DESIGN:
        pf["design"] = F.DESIGN[c]
    elif c:
        extra["condition"] = c
    for a in it.get("amenities") or []:
        if a in F.AMENITY:
            pf.setdefault("amenities", []).append(F.AMENITY[a])
        else:
            extra.setdefault("amenities", []).append(a)
    if months := [int(m) for m in it.get("months") or []]:
        pf["months"], pf["periods"] = months, [f"{m}Month" for m in months if m in MONTHS]
    if it.get("period"):
        pf["period"] = it["period"]
        if it["period"] == "day":
            pf["periods"] = ["1Day"]
    for k in ("headline", "tenants", "deposit", "approx"):
        if it.get(k) not in (None, "", 0):
            pf[k] = int(it[k]) if k in ("tenants", "deposit") else it[k]
    if extra:
        pf["site_extra"] = extra
    return pf


def common(it: dict) -> dict:
    try:
        pub = datetime.fromisoformat(it["published_at"]) if it.get("published_at") else None
    except ValueError:
        pub = None
    return {"price": it.get("price"), "currency": it.get("currency") or "USD", "lat": it.get("lat"), "lng": it.get("lon"),
            "description": it.get("description") or None, "post_url": it.get("post_url") or None, "published_at": pub}


def fetch(path: str) -> tuple[str, bytes] | None:
    url = path if path.startswith("http") else PHOTO_BASE + path.lstrip("/")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            data = r.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise ValueError("empty or too large")
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        return (ext if ext in P.PHOTO_EXT else ".jpg"), data
    except Exception as e:
        log.warning("photo skipped %s: %s", url, e)
        return None


def download(it: dict) -> list[tuple[str, bytes]]:
    with ThreadPoolExecutor(3) as ex:
        return [g for g in ex.map(fetch, (it.get("photos") or [])[:MAX_PHOTOS]) if g]


def exists(db: Session, sid: str) -> bool:
    return bool(db.scalar(select(Property.id).where(Property.post_fields["site_id"].astext == sid))
                or db.scalar(select(SaleObject.id).where(SaleObject.site_id == sid))
                or db.scalar(select(Car.id).where(Car.site_id == sid)))


def existing_rent(db: Session, url: str | None) -> Property | None:
    if not url:
        return None
    pid = (db.scalar(select(Property.id).where(Property.post_url == url).limit(1))
           or db.scalar(select(PropertyPublication.property_id).where(PropertyPublication.url == url).limit(1))
           or db.scalar(select(ChannelPost.property_id).where(ChannelPost.link == url, ChannelPost.property_id.is_not(None)).limit(1)))
    return db.get(Property, pid) if pid else None


def one(db: Session, it: dict, photos: bool) -> tuple[str, int]:
    """-> ("created" | "matched", photos stored). Commits nothing."""
    kind, c = target(it), common(it)
    got = download(it) if photos else []
    if kind == "rent":
        msg = re.search(r"/(\d+)/?$", c["post_url"] or "")
        p = existing_rent(db, c["post_url"])
        if p:
            p.post_fields = {**(p.post_fields or {}), **{k: v for k, v in rent_fields(it).items() if k in ("service", "site_id")}}
            outcome = "matched"
            got = got if not db.scalar(select(PropertyMedia.id).where(PropertyMedia.property_id == p.id, PropertyMedia.kind == "photo").limit(1)) else []
        else:
            p = Property(source_type="channel", status="published", is_exclusive=bool(it.get("exclusive")), post_fields=rent_fields(it),
                         address=it.get("title"), district=it.get("district"), bedrooms=it.get("rooms"), area=it.get("area"),
                         floor=it.get("floor"), total_floors=it.get("floors"), post_message_id=msg[1] if msg else None,
                         **{k: v for k, v in c.items() if v is not None})
            db.add(p)
            db.flush()
            log_event(db, "property", p.id, "imported_from_site", None, site_id=it["id"])
            outcome = "created"
            if c["post_url"]:
                P.record_publication(db, p, "tg", c["post_url"], p.post_message_id)
        for pos, (ext, data) in enumerate(got):
            key = f"properties/{p.id}/{uuid.uuid4().hex}{ext}"
            storage.put(key, data)
            storage.put_preview(key, data)
            db.add(PropertyMedia(property_id=p.id, kind="photo", path=key, position=pos))
        return outcome, len(got)
    if kind == "sale":
        pf = {k: v for k, v in rent_fields(it).items() if k not in ("service", "site_id", "months", "periods", "period")}
        o = SaleObject(service=it["service"], title=it["title"], district=it.get("district"), rooms=it.get("rooms"),
                       area=it.get("area"), floor=it.get("floor"), floors=it.get("floors"), completion=it.get("completion"),
                       post_fields={**pf, "deal": "Sale", "prop_type": pf.get("prop_type") or "Apartment"},
                       is_exclusive=bool(it.get("exclusive")))
    else:
        o = Car(deal=it["deal"], period=it.get("period"), title=it["title"], deposit=it.get("deposit"), year=it.get("year"),
                gearbox=it.get("gearbox"), fuel=it.get("fuel"), body=it.get("body"), seats=it.get("seats"),
                mileage=int(it["mileage"]) if it.get("mileage") else None, pickup=it.get("pickup"),
                is_exclusive=bool(it.get("exclusive")))
    for k, v in c.items():
        setattr(o, k, v)
    o.site_id, o.status = it["id"], "published"
    db.add(o)
    db.flush()
    for ext, data in got:
        key = f"offers/{'s' if kind == 'sale' else 'c'}{o.id}/{uuid.uuid4().hex}{ext}"
        storage.put(key, data)
        storage.put_preview(key, data)
        o.photos = [*o.photos, key]
    return "created", len(got)


def run(db: Session, items: list[dict], dry_run: bool = False) -> dict:
    stat = {k: Counter() for k in ("created", "matched", "skipped", "photos")}
    for it in items:
        svc = it.get("service") or "?"
        if not it.get("id") or not it.get("service") or exists(db, it["id"]):
            stat["skipped"][svc] += 1
            continue
        try:
            with db.begin_nested():
                outcome, n = one(db, it, not dry_run)
        except Exception as e:  # one bad item never stops the import
            log.warning("skipped %s: %s", it.get("id"), e)
            stat["skipped"][svc] += 1
            continue
        stat[outcome][svc] += 1
        stat["photos"][svc] += n
    (db.rollback if dry_run else db.commit)()
    print(("DRY RUN (nothing written)\n" if dry_run else "") + f"{'service':<12}{'created':>8}{'matched':>8}{'photos':>8}{'skipped':>8}")
    for svc in sorted({s for c in stat.values() for s in c}):
        print(f"{svc:<12}" + "".join(f"{stat[k][svc]:>8}" for k in ("created", "matched", "photos", "skipped")))
    print(f"{'total':<12}" + "".join(f"{sum(stat[k].values()):>8}" for k in ("created", "matched", "photos", "skipped")))
    return {k: dict(v) for k, v in stat.items()}


def main():
    ap = argparse.ArgumentParser(description="one-off import of hge.ge listings.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source", default=SOURCE, help="URL or path of listings.json")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if re.match(r"https?://", a.source):
        with urllib.request.urlopen(urllib.request.Request(a.source, headers=UA), timeout=60) as r:
            data = json.load(r)
    else:
        data = json.load(open(a.source, encoding="utf-8"))
    with SessionLocal() as db:
        run(db, data["items"] if isinstance(data, dict) else data, a.dry_run)


if __name__ == "__main__":
    main()
