"""One-time import of the site hge.ge's objects (its listings.json: rent, sale, commercial, daily, new, cars) into the CRM.

    python -m app.importers.site_catalog [--source URL_OR_PATH] [--dry-run] [--no-photos]

From then on the site reads only the CRM (app/api/site.py). Idempotent: an object is matched by its old site id
(post_fields.site_id) or its channel post link (Property.post_url, a publication's url, channel_posts.link); a matched
object only gets the missing service / site_id / deal, its EMPTY columns filled and photos if it has none. Never an
owner, never an overwrite of what an agent entered. Photos (max 9) are downloaded from https://hge.ge/<path> and stored
like agent uploads (properties/<id>/<uuid>.<ext>, kind photo). --dry-run writes nothing (and downloads nothing)."""
import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.db import SessionLocal
from app.models import ChannelPost, Property, PropertyMedia, PropertyPublication
from app.services import properties as P
from app.services import site_feed as F
from app.services.common import log_event

log = logging.getLogger("site_catalog")
SOURCE = "https://hge.ge/data/listings.json"
PHOTO_BASE = "https://hge.ge/"
MAX_PHOTOS, WORKERS, TIMEOUT, MAX_BYTES = P.MAX_MEDIA["photo"], 3, 25, 15 * 1024 * 1024
UA = {"User-Agent": "HomesInGeorgiaImport/1.0"}
MONTHS = {1, 2, 3, 4, 5, 6, 9, 12}  # the generator's periods; longer ones (24, 36, 60) live in post_fields.months only


def load(source: str) -> list[dict]:
    if re.match(r"https?://", source):
        with urllib.request.urlopen(urllib.request.Request(source, headers=UA), timeout=60) as r:
            data = json.load(r)
    else:
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
    return data["items"] if isinstance(data, dict) else data


def post_fields_of(it: dict) -> dict:
    """The site item's facts as post_fields: the generator's CRM tags where they exist, the rest under SITE_KEYS."""
    pf, extra = {}, {}
    sale = it.get("deal") == "sale"
    pf["service"], pf["site_id"], pf["deal"] = it["service"], it["id"], "Sale" if sale else "Rent"
    if it.get("source") and it["source"] != it["service"]:
        pf["site_source"] = it["source"]
    if it.get("kind") in F.KIND:
        pf["prop_type"] = F.KIND[it["kind"]]
    for key, tbl, src in (("building", F.BUILDING, "building"), ("heating", F.HEATING, "heating"), ("pets", F.PETS, "pets")):
        if it.get(src):
            if it[src] in tbl:
                pf[key] = tbl[it[src]]
            else:
                extra[src] = it[src]
    if it.get("metro"):
        if it["metro"] in F.METRO:
            pf["metro"] = F.METRO[it["metro"]]
        else:
            extra["metro"] = it["metro"]
    c = it.get("condition")
    if c in F.FRAME:
        pf["condition"] = F.FRAME[c]
    elif c == "renovated" and sale:
        pf["condition"] = "FullyRenovated"
    elif c in F.DESIGN:
        pf["design"] = F.DESIGN[c]
    elif c:
        extra["condition"] = c
    am = []
    for a in it.get("amenities") or []:
        if a in F.AMENITY:
            am.append(F.AMENITY[a])
        else:
            extra.setdefault("amenities", []).append(a)
    if am:
        pf["amenities"] = am
    months = [int(m) for m in it.get("months") or []]
    if months:
        pf["months"] = months
        pf["periods"] = [f"{m}Month" for m in months if m in MONTHS]
    if it.get("period"):
        pf["period"] = it["period"]
        if it["period"] == "day":
            pf["periods"] = ["1Day"]
    for k in ("headline", "completion", "tenants", "deposit"):
        if it.get(k) not in (None, "", 0):
            pf[k] = int(it[k]) if k in ("tenants", "deposit") else it[k]
    if sale and it.get("price_usd"):
        pf["sale_price"] = int(it["price_usd"])
    if it.get("ppsqm_usd"):
        pf["ppsqm_usd"] = it["ppsqm_usd"]
    if it.get("approx"):
        pf["approx"] = True
    if it["service"].startswith("car"):
        pf["car"] = {k: it[k] for k in ("year", "gearbox", "fuel", "body", "seats", "mileage") if it.get(k) not in (None, "")}
        pf["car"]["title"] = it.get("title") or "Car"
    if extra:
        pf["site_extra"] = extra
    return {k: v for k, v in pf.items() if v not in (None, "", [], {})}


def columns_of(it: dict) -> dict:
    car = it["service"].startswith("car")
    msg = re.search(r"/(\d+)/?$", it.get("post_url") or "")
    pub = None
    try:
        pub = datetime.fromisoformat(it["published_at"]) if it.get("published_at") else None
    except ValueError:
        pass
    return {"address": (it.get("pickup") if car else it.get("title")) or None, "district": it.get("district") or None,
            "lat": it.get("lat"), "lng": it.get("lon"), "price": it.get("price"), "currency": it.get("currency") or "USD",
            "bedrooms": it.get("rooms"), "area": it.get("area"), "floor": it.get("floor"), "total_floors": it.get("floors"),
            "description": it.get("description") or None, "post_url": it.get("post_url") or None,
            "post_message_id": msg[1] if msg else None, "published_at": pub}


def find(db: Session, it: dict) -> Property | None:
    if pid := db.scalar(select(Property.id).where(Property.post_fields["site_id"].astext == it["id"])):
        return db.get(Property, pid)
    if not (url := it.get("post_url")):
        return None
    pid = (db.scalar(select(Property.id).where(Property.post_url == url).limit(1))
           or db.scalar(select(PropertyPublication.property_id).where(PropertyPublication.url == url).limit(1))
           or db.scalar(select(ChannelPost.property_id).where(ChannelPost.link == url, ChannelPost.property_id.is_not(None)).limit(1)))
    return db.get(Property, pid) if pid else None


def fetch(path: str) -> tuple[str, bytes] | None:
    url = path if path.startswith("http") else PHOTO_BASE + path.lstrip("/")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
            data = r.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise ValueError("empty or too large")
        return os.path.splitext(url.split("?")[0])[1].lower() or ".jpg", data
    except Exception as e:
        log.warning("photo skipped %s: %s", url, e)
        return None


def store_photos(db: Session, p: Property, paths: list[str]) -> int:
    with ThreadPoolExecutor(WORKERS) as ex:
        got = [g for g in ex.map(fetch, paths[:MAX_PHOTOS]) if g]
    for pos, (ext, data) in enumerate(got):
        if ext not in P.PHOTO_EXT:
            ext = ".jpg"
        key = f"properties/{p.id}/{uuid.uuid4().hex}{ext}"
        storage.put(key, data)
        storage.put_preview(key, data)
        db.add(PropertyMedia(property_id=p.id, kind="photo", path=key, position=pos))
    return len(got)


def has_photos(db: Session, p: Property) -> bool:
    return db.scalar(select(PropertyMedia.id).where(PropertyMedia.property_id == p.id, PropertyMedia.kind == "photo").limit(1)) is not None


def import_item(db: Session, it: dict, photos: bool) -> tuple[str, int]:
    """-> ("created" | "matched", photos stored). Commits nothing."""
    pf, cols = post_fields_of(it), columns_of(it)
    p = find(db, it)
    if p is None:
        p = Property(source_type="channel", status="published", is_exclusive=bool(it.get("exclusive")), post_fields=pf,
                     **{k: v for k, v in cols.items() if v is not None})
        db.add(p)
        db.flush()
        log_event(db, "property", p.id, "imported_from_site", None, site_id=it["id"])
        outcome = "created"
    else:
        cur = dict(p.post_fields or {})
        add = {k: pf[k] for k in ("service", "site_id", "deal") if k in pf and not cur.get(k)}
        if add:
            p.post_fields = {**cur, **add}
        for k, v in cols.items():
            if k != "currency" and v is not None and getattr(p, k) in (None, ""):
                setattr(p, k, v)
        outcome = "matched"
    if cols["post_url"] and not db.scalar(select(PropertyPublication.id).where(
            PropertyPublication.property_id == p.id, PropertyPublication.url == cols["post_url"])):
        P.record_publication(db, p, "tg", cols["post_url"], cols["post_message_id"])
    n = 0
    if photos and it.get("photos") and not has_photos(db, p):
        n = store_photos(db, p, it["photos"])
    return outcome, n


def run(db: Session, items: list[dict], dry_run: bool = False, photos: bool = True, out=print) -> dict:
    stat = {"created": Counter(), "matched": Counter(), "photos": Counter(), "skipped": Counter()}
    for it in items:
        svc = it.get("service") or "?"
        if not it.get("id") or not it.get("service"):
            stat["skipped"][svc] += 1
            continue
        try:
            with db.begin_nested():
                outcome, n = import_item(db, it, photos and not dry_run)
        except Exception as e:  # one bad item never stops the import
            log.warning("skipped %s: %s", it.get("id"), e)
            stat["skipped"][svc] += 1
            continue
        stat[outcome][svc] += 1
        stat["photos"][svc] += n
    (db.rollback if dry_run else db.commit)()
    out(("DRY RUN (nothing written)\n" if dry_run else "") + f"{'service':<12}{'created':>8}{'matched':>8}{'photos':>8}{'skipped':>8}")
    for svc in sorted({s for c in stat.values() for s in c}):
        out(f"{svc:<12}{stat['created'][svc]:>8}{stat['matched'][svc]:>8}{stat['photos'][svc]:>8}{stat['skipped'][svc]:>8}")
    out(f"{'total':<12}" + "".join(f"{sum(stat[k].values()):>8}" for k in ("created", "matched", "photos", "skipped")))
    return {k: dict(v) for k, v in stat.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default=SOURCE, help="URL or path of listings.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-photos", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    items = load(a.source)
    with SessionLocal() as db:
        run(db, items, a.dry_run, not a.no_photos)


if __name__ == "__main__":
    main(sys.argv[1:])
