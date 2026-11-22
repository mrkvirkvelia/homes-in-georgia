"""Копии объекта на myhome (David 11-22, Stanislav: «по адресу, метражу»): the parser keeps only owners' fresh ads, so
agents' copies of an exclusive (the owner's photos re-posted 30 times) never reached «Похожие». For one object a
narrow myhome search is made — its district, the rooms, the area ±12 %, agents included — then every rental on its
street with the same rooms and area; the ads found are kept as listings with status «copy» (never shown to clients,
not marked gone by the parser's sync) with their photos' dHash, so «Похожие» scores them like any other ad
(shared photos, the house, floor, area). Run for exclusives when they are taken / published, and by the card's button."""
import json
import logging
import re
import time

from sqlalchemy.orm import Session

from app import districts
from app.models import Listing, Property
from app.services.common import now
from app.services.dedup import _same_street, street_house, street_words

log = logging.getLogger(__name__)
SEARCH = "https://www.myhome.ge/en/real-estate/?deal_types=2&real_estate_types=1&cities=1&currency_id=2&{}"
PAGES = 5           # myhome renders at most 5 pages (120 ads) of one search
AREA_TOL = 0.12
PHOTOS = 6          # photos per ad to hash: enough to catch the copied ones, few downloads
STATUS = "copy"


def _page(query: str) -> list[dict] | None:
    from curl_cffi import requests
    html = requests.get(SEARCH.format(query), impersonate="chrome", timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    qs = json.loads(m.group(1))["props"]["pageProps"]["dehydratedState"]["queries"]
    q = next((q for q in qs if q["queryKey"][:2] == ["statements", "list"]), None)
    return q["state"]["data"]["data"]["data"] if q else None


def search(query: str, pause: float = 1.0) -> list[dict]:
    out = []
    for n in range(1, PAGES + 1):
        items = _page(f"{query}&page={n}")
        if not items:
            break
        out += items
        if len(items) < 24:
            break
        time.sleep(pause)
    return out


def _street(addr) -> frozenset:
    """The street words of an address with or without a house number (myhome: «რამიშვილი ნ. ქ. » often has none)."""
    return street_house(addr)[0] or street_words(addr)


def _filters(p: Property) -> str:
    q = []
    rooms = p.rooms or (p.bedrooms + 1 if p.bedrooms is not None else None)  # myhome «2 room» = 1 bedroom + living
    if rooms:
        q.append(f"room_types={min(int(rooms), 6)}")
    if p.area:
        a = float(p.area)
        q.append(f"area_from={int(a * (1 - AREA_TOL))}&area_to={int(a * (1 + AREA_TOL)) + 1}")
    return "&".join(q)


def candidates(p: Property, pause: float = 1.0) -> list[dict]:
    """myhome ads that could be the object: the city narrowed by rooms and area tells myhome's ids of the object's
    district and street; then the district and the street, each with the rooms and area (≤ 120 ads a search)."""
    base = _filters(p)
    tag, street = districts.tag(p.district), _street(p.address)
    found = {i["id"]: i for i in search(base, pause)}

    def ours(i):
        return (tag and districts.tag(i.get("urban_name")) == tag) or \
            (street and _same_street(street, _street(i.get("address"))))
    urbans = {i["urban_id"] for i in found.values() if tag and i.get("urban_id") and districts.tag(i.get("urban_name")) == tag}
    for uid in list(urbans)[:2]:
        found.update({i["id"]: i for i in search(f"urbans={uid}&{base}", pause)})
    streets = {i["street_id"] for i in found.values() if street and i.get("street_id")
               and _same_street(street, _street(i.get("address")))}
    for sid in list(streets)[:3]:  # the object's street, whatever district myhome files it under
        found.update({i["id"]: i for i in search(f"streets={sid}&{base}", pause)})
    def floor_fits(i):  # agents copy the floor with the photos; ±1: «8» / «8-9» / a slip
        return p.floor is None or i.get("floor") is None or abs(int(i["floor"]) - int(p.floor)) <= 1
    return [i for i in found.values() if ours(i) and floor_fits(i)]


def _usd(i: dict) -> int | None:
    pr = (i.get("price") or {}).get("2") or {}
    return int(pr["price_total"]) if pr.get("price_total") else None


def _hashes(urls: list[str]) -> list[int]:
    import httpx

    from app.services.matching import photo_hash
    out = []
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        for u in urls[:PHOTOS]:
            try:
                h = photo_hash(c.get(u).raise_for_status().content)
            except httpx.HTTPError:
                h = None
            out.append((h & ((1 << 64) - 1)) if h is not None else 0)
    return out


def save(db: Session, items: list[dict]) -> int:
    """Upsert the ads as listings (an ad the parser already has keeps its status, a gone one becomes a «copy")."""
    n, t = 0, now().isoformat(timespec="seconds")
    for i in items:
        lid = f"mh{i['id']}"
        photos = [x.get("large") for x in i.get("images") or [] if x.get("large")]
        l = db.get(Listing, lid)
        if l is None:
            l = Listing(id=lid, source="myhome.ge", status=STATUS, first_seen=t)
            db.add(l)
        elif l.status not in ("gone", STATUS):
            continue  # a live ad of the parser: «Похожие» sees it already
        l.status = STATUS
        l.urls = json.dumps([f"https://www.myhome.ge/pr/{i['id']}/{i.get('dynamic_slug') or ''}"])
        l.address, l.area, l.floor = i.get("address"), i.get("area"), i.get("floor")
        l.bedrooms = int(i["bedroom"]) if str(i.get("bedroom") or "").isdigit() else None
        l.district = districts.label(i.get("urban_name")) or i.get("urban_name")
        l.price_usd = _usd(i)
        l.text = re.sub(r"<br\s*/?>", "\n", i.get("comment") or i.get("dynamic_title") or "")
        if l.photos != json.dumps(photos):
            l.photos, l.photo_hashes = json.dumps(photos), json.dumps(_hashes(photos))
        l.last_seen = l.updated_at = t
        n += 1
    db.commit()
    return n


def recent(db: Session, pid: int, hours: int = 24) -> bool:
    from datetime import timedelta

    from sqlalchemy import select

    from app.models import Event
    return db.scalar(select(Event.id).where(Event.entity == "property", Event.entity_id == str(pid),
                                            Event.action == "myhome_copies", Event.at > now() - timedelta(hours=hours))
                     .limit(1)) is not None


def run(db: Session, pid: int, pause: float = 1.0) -> int:
    """Job myhome_copies: search, save -> how many ads were saved (an event on the object says when)."""
    from app.services.common import log_event
    p = db.get(Property, pid)
    if p is None or not (p.area or p.bedrooms is not None or p.rooms):
        return 0
    items = candidates(p, pause)
    n = save(db, items)
    log_event(db, "property", pid, "myhome_copies", None, label="поиск копий на myhome", candidates=len(items), saved=n)
    db.commit()
    log.info("myhome copies of #%s: %s candidates, %s saved", pid, len(items), n)
    return n
