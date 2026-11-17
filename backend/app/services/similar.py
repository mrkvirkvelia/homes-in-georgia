"""«Похожие объекты» everywhere (Stanislav 11-17): one flat must never be worked twice — one agent takes an ss.ge ad
while Vika has already posted the same flat in the channel, the area / floor differ a little, the photos are the same.

For an ad or an object, every candidate across the whole base: our objects (any status, the archive too) and the live
outside ads (ss / myhome / livo / korter / Facebook / Telegram, competitors' too) not linked to an object yet (a
linked ad is its object). Signals, each with a reason in Russian for the agent:
- strong («почти точно»): the same link, the same cadastral code, 2+ shared photos (dHash), the owner's phone and the
  same house / floor, a pair someone already marked «Дубль»;
- medium: one shared photo, the owner's phone alone, the same owner name, the same house, a pin within NEAR_M,
  the same author on the same site;
- parameters: bedrooms, floor, area (±AREA_TOL), price (±PRICE_TOL), district.
Shown: anything strong; one shared photo or the owner's phone alone; another medium signal with 1+ matching
parameter; or a «twin» nearby (the same district or within TWIN_KM, bedrooms and area agree, and the floor or the
price too). Loose on purpose: the agent decides «Дубль» /
«Не дубль» (decide()); a pair called different is not shown again.

ponytail: the whole base and every live ad in memory per call (photos through a pigeonhole index, so ~10k ads stay
well under a second); cache the profiles for a minute if it shows in the request log.
"""
import json
import logging
import math
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Listing, Owner, Property, PropertyListing, PropertyMedia, SimilarDecision, User
from app.services import properties as P
from app.services.common import jload, log_event, now
from app.services.dedup import _same_street, extract_phones, phone_match, relation, street_house, street_words
from app.services.errors import DomainError

log = logging.getLogger(__name__)

PHOTO_BITS = 4       # dHash distance of «the same photo» (matching.PHOTO_BITS)
U64 = (1 << 64) - 1
AREA_TOL = 0.12      # «площадь почти та же»: 52 vs 57 m² still shows (11-17: the same flat, the area differs a little)
PRICE_TOL = 0.12
NEAR_M = 80          # pins this close: the same building, give or take the geocoder
TWIN_KM = 1.5        # a twin (bedrooms + area + floor / price) this far still shows: ad pins can be a district off
LIVE = ("published", "pending_review")
CADASTRAL = re.compile(r"(?<![\d.])\d{2}\.\d{2}\.\d{2}\.\d{3}\.\d{3}(?:\.\d{2}\.\d{3})?(?![\d])")
GEL_USD, EUR_USD = 0.37, 1.08  # rough: only for «цена близкая» (±12%)
SOURCE_NAME = {"ss": "ss.ge", "myhome": "myhome.ge", "livo": "livo.ge", "korter": "korter.ge", "facebook": "Facebook",
               "instagram": "Instagram", "threads": "Threads", "telegram": "Telegram", "agency": "канал агентства"}


def key(kind: str, ident) -> str:
    return f"{kind}:{ident}"


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _name_tokens(s) -> frozenset:
    """«Нино Беридзе» → {нино, беридзе}; short words and «собственник» / «owner» say nothing."""
    words = re.findall(r"[a-zа-яёა-ჰ]{3,}", str(s or "").lower())
    return frozenset(w for w in words if w not in {"собственник", "хозяин", "owner", "agent", "агент", "без", "посредников"})


def _bare_street(addr) -> frozenset:
    """The street of an address without a house number («Vake mckheta st. -»), else empty."""
    return street_words(addr) if street_house(addr)[1] is None else frozenset()


def _hashes(raw) -> list[int]:
    try:
        return [int(h) for h in (jload(raw, []) if isinstance(raw, str) or raw is None else raw) or []]
    except (TypeError, ValueError):
        return []


def _usd(price, currency) -> float | None:
    if not price:
        return None
    return float(price) * {"GEL": GEL_USD, "EUR": EUR_USD}.get(currency or "USD", 1.0)


def _km(a, b) -> float | None:
    if None in (a[0], a[1], b[0], b[1]):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------- profiles

def _ad_source(l: Listing, competitors: set[str]) -> str:
    if l.source in competitors:
        return "конкурент · " + l.source.split(":", 1)[-1]
    return SOURCE_NAME.get(P.source_type_of(l), l.source)


def _listing_profile(l: Listing, competitors: set[str]) -> dict:
    t = l.text or ""
    urls = jload(l.urls, []) or []
    n_photos = len(jload(l.photos, []) or [])
    return {
        "key": key("l", l.id), "kind": "ad", "listing_id": l.id, "property_id": None,
        "urls": set(urls), "phones": extract_phones(t), "names": frozenset(), "author": (l.source, l.owner_id) if l.owner_id else None,
        "cads": {_digits(c) for c in CADASTRAL.findall(t)}, "hashes": _hashes(l.photo_hashes),
        "house": street_house(l.address), "street": _bare_street(l.address), "at": (l.lat, l.lng), "district": l.district,
        "floor": l.floor, "area": float(l.area) if l.area else None, "bedrooms": l.bedrooms,
        "price_usd": float(l.price_usd) if l.price_usd else None,
        "out": {"kind": "ad", "listing_id": l.id, "property_id": None, "where": _ad_source(l, competitors),
                "competitor": l.source in competitors, "status": l.status, "address": l.address, "district": l.district,
                "bedrooms": l.bedrooms, "area": l.area, "floor": l.floor, "price_usd": l.price_usd,
                "photos": [f"/api/listing-photos/{l.id}/{i}" for i in range(min(n_photos, 6))],
                "url": urls[0] if urls else None, "seen": l.last_seen},
    }


def _objects(db: Session, pids: list[int] | None = None) -> list[dict]:
    """Profiles of our objects: the owner's phone and name, every link and photo hash of the object and its ads."""
    q = select(Property) if pids is None else select(Property).where(Property.id.in_(pids))
    props = list(db.scalars(q))
    if not props:
        return []
    ids = [p.id for p in props]
    owners = {o.id: o for o in db.scalars(select(Owner).where(Owner.id.in_({p.owner_id for p in props if p.owner_id})))}
    agents = dict(db.execute(select(User.id, User.name).where(User.id.in_({p.agent_id for p in props if p.agent_id}))).all()) \
        if any(p.agent_id for p in props) else {}
    ads: dict[int, list] = {}
    for pid, url, l in db.execute(select(PropertyListing.property_id, PropertyListing.url, Listing)
                                  .join(Listing, Listing.id == PropertyListing.listing_id)
                                  .where(PropertyListing.property_id.in_(ids))):
        ads.setdefault(pid, []).append((url, l))
    photos: dict[int, list[str]] = {}
    own: dict[int, list[int]] = {}  # property_media.dhash (matching.photo_hash), signed in the DB
    for pid, path, h in db.execute(select(PropertyMedia.property_id, PropertyMedia.path, PropertyMedia.dhash)
                                   .where(PropertyMedia.property_id.in_(ids), PropertyMedia.kind == "photo")
                                   .order_by(PropertyMedia.position, PropertyMedia.id)):
        photos.setdefault(pid, []).append(path)
        if h:  # 0: unreadable (matching.backfill_media_hashes)
            own.setdefault(pid, []).append(h & U64)
    out = []
    for p in props:
        o = owners.get(p.owner_id)
        mine = ads.get(p.id, [])
        origin = next((l for _, l in mine if l.id == p.listing_id), None)
        urls = {p.source_url} | {u for u, _ in mine} | {u for _, l in mine for u in jload(l.urls, []) or []}
        hashes = own.get(p.id, []) + [h for _, l in mine for h in _hashes(l.photo_hashes)]
        phones = [o.phone] if o and o.phone else []
        phones += [x for _, l in mine for x in extract_phones(l.text or "")]
        at = (p.lat, p.lng) if p.lat is not None else (origin.lat, origin.lng) if origin is not None else (None, None)
        pics = [f"/api/media/{x}" for x in photos.get(p.id, [])[:6]] or \
            ([f"/api/listing-photos/{origin.id}/{i}" for i in range(min(len(jload(origin.photos, []) or []), 6))] if origin else [])
        out.append({
            "key": key("p", p.id), "kind": "object", "listing_id": None, "property_id": p.id, "ad_ids": {l.id for _, l in mine},
            "urls": urls - {None, ""}, "phones": list(dict.fromkeys(phones)), "names": _name_tokens(o.name) if o else frozenset(),
            "author": None, "cads": {_digits(p.cadastral_code)} - {""}, "hashes": hashes,
            "house": street_house(p.address), "street": _bare_street(p.address), "at": at, "district": p.district, "floor": p.floor,
            "area": float(p.area) if p.area is not None else None, "bedrooms": p.bedrooms, "price_usd": _usd(p.price, p.currency),
            "agent_id": p.agent_id,
            "out": {"kind": "object", "listing_id": None, "property_id": p.id, "where": "наша база", "competitor": False,
                    "status": p.status, "address": p.address, "district": p.district, "bedrooms": p.bedrooms,
                    "area": float(p.area) if p.area is not None else None, "floor": p.floor,
                    "price_usd": round(_usd(p.price, p.currency)) if p.price else None,
                    "photos": pics, "url": p.post_url, "agent": agents.get(p.agent_id), "is_exclusive": p.is_exclusive,
                    "seen": p.updated_at.isoformat() if p.updated_at else None},
        })
    return out


# parsing ~10k ads and indexing their photos is most of a call: kept per process until an ad changes (count / last
# update of the live ads) or the competitor list does
_cache: dict = {"stamp": None, "ads": [], "idx": {}}


def _ads(db: Session, competitors: set[str]) -> tuple[list[dict], dict]:
    """Live outside ads (profiles, their photo index); the caller drops the ones linked to an object since."""
    live = (Listing.status.in_(LIVE), Listing.source.not_in(("object", "agency")))
    stamp = (*db.execute(select(func.count(), func.max(Listing.updated_at)).where(*live)).one(), frozenset(competitors))
    if stamp != _cache["stamp"]:
        ads = [_listing_profile(l, competitors) for l in db.scalars(select(Listing).where(*live))]
        _cache.update(stamp=stamp, ads=ads, idx=_photo_index(ads))
    return _cache["ads"], _cache["idx"]


# ---------------------------------------------------------------- photos

def _photo_index(cands: list[dict]) -> dict:
    """Pigeonhole: two hashes ≤ 4 bits apart share at least one of 5 equal 13-bit chunks."""
    idx: dict[tuple, set] = {}
    for n, c in enumerate(cands):
        for h in c["hashes"]:
            for i in range(5):
                idx.setdefault((i, (h >> (i * 13)) & 0x1FFF), set()).add(n)
    return idx


def _shared(a: list[int], b: list[int]) -> int:
    return sum(1 for x in a if any(bin(x ^ y).count("1") <= PHOTO_BITS for y in b))


# ---------------------------------------------------------------- the verdict

def _fits(s: dict, c: dict) -> bool:
    """What both know roughly agrees: bedrooms, floor ±1, area ±10% (properties.could_be_same on profiles)."""
    def known(k):
        return s[k] is not None and c[k] is not None
    return not ((known("bedrooms") and int(s["bedrooms"]) != int(c["bedrooms"]))
                or (known("floor") and abs(int(s["floor"]) - int(c["floor"])) > 1)
                or (s["area"] and c["area"] and abs(s["area"] - c["area"]) > max(1.0, 0.10 * max(s["area"], c["area"]))))


def _street(s: dict, c: dict) -> bool:
    """One address names no house, the other one is on its street (11-17: «Vake mckheta st. -» / 45 Mtskheta)."""
    return (bool(s.get("street")) and c["house"][1] is not None and _same_street(s["street"], c["house"][0])) or \
        (bool(c.get("street")) and s["house"][1] is not None and _same_street(c["street"], s["house"][0]))


def _exact(s: dict, c: dict) -> bool:
    """A twin by params: the same bedrooms and floor, the area to 3%."""
    return (s["bedrooms"] is not None and s["bedrooms"] == c["bedrooms"] and s["floor"] is not None
            and s["floor"] == c["floor"] and bool(s["area"] and c["area"])
            and abs(s["area"] - c["area"]) <= max(1.0, 0.03 * max(s["area"], c["area"])))


def compare(s: dict, c: dict, shared: int = 0) -> tuple[str | None, float, list[str]]:
    """(same | maybe | None, score, reasons) of candidate c for subject s."""
    strong, medium, params = [], [], []
    if s["urls"] & c["urls"]:
        strong.append("та же ссылка")
    if s["cads"] & c["cads"]:
        strong.append("тот же кадастровый код")
    if shared >= 2:
        strong.append(f"общих фото: {shared}")
    elif shared == 1:
        medium.append("одно общее фото")
    rel = relation(s["house"], c["house"])
    same_house = rel == "тот же дом"
    # an agent's number (behind 3+ objects, find() drops it from the profiles) names no flat
    phone = any(phone_match(x, y) for x in s["phones"] for y in c["phones"])
    same_floor = s["floor"] is not None and c["floor"] is not None and int(s["floor"]) == int(c["floor"])
    if phone and (same_house or same_floor):
        strong.append("тот же телефон собственника" + (" и дом" if same_house else " и этаж"))
    elif phone:
        medium.append("тот же телефон собственника")
    if s["names"] and c["names"] and len(s["names"] & c["names"]) >= min(2, len(s["names"]), len(c["names"])):
        medium.append("то же имя собственника")
    if s["author"] and s["author"] == c["author"]:
        medium.append("тот же автор объявления")
    if same_house and not phone:
        medium.append("тот же дом")
    elif rel and not same_house:
        params.append(rel)
    km = _km(s["at"], c["at"])
    if km is not None and km * 1000 <= NEAR_M and not same_house:
        medium.append(f"рядом на карте, {round(km * 1000)} м")
    if s["bedrooms"] is not None and c["bedrooms"] is not None and int(s["bedrooms"]) == int(c["bedrooms"]):
        params.append("спальни совпадают")
    if same_floor:
        params.append("этаж совпадает")
    if s["area"] and c["area"]:
        a, b = s["area"], c["area"]
        if abs(a - b) <= AREA_TOL * max(a, b):
            params.append("площадь та же" if abs(a - b) <= 1 else f"площадь близкая ({a:g} / {b:g} м²)")
    if s["price_usd"] and c["price_usd"]:
        a, b = s["price_usd"], c["price_usd"]
        if abs(a - b) <= PRICE_TOL * max(a, b):
            params.append("цена близкая")
    same_district = bool(s["district"]) and s["district"] == c["district"]
    core = {"спальни совпадают", "этаж совпадает", "цена близкая"} | {x for x in params if x.startswith("площадь")}
    n_core = len(core & set(params))
    if strong:
        level = "same"
    elif medium and _fits(s, c):
        # a shared photo, the phone, the house, a pin next door…: the agent looks when the flat can be this one —
        # bedrooms, floor ±1, area ±10% (11-17: 100 m² / 6th vs 110 m² / 5th). Without that fit these were another flat
        # 548 times of 552 on the prod sample (eval 11-17)
        level = "maybe"
    elif (rel or _street(s, c)) and _exact(s, c):
        level = "maybe"  # a house next door, or the street of an ad without a number, with the same floor and area
        if not rel:
            params.append("та же улица")
    elif (same_district or (km is not None and km <= TWIN_KM)) and _exact(s, c) and "цена близкая" in params:
        level = "maybe"  # a twin: the same bedrooms, floor, area and price (a looser twin: 0 of 176 in the eval)
        if same_district:
            params.append("тот же район")
    else:
        return None, 0.0, []
    score = 10 * len(strong) + 3 * len(medium) + n_core + (shared or 0)
    return level, float(score), strong + medium + params


# ---------------------------------------------------------------- finding

def _decisions(db: Session, k: str) -> dict[str, dict]:
    out = {}
    for d in db.scalars(select(SimilarDecision).where(or_(SimilarDecision.a == k, SimilarDecision.b == k))):
        out[d.b if d.a == k else d.a] = {"verdict": d.verdict, "by": d.decided_by, "at": d.decided_at.isoformat()}
    return out


def find(db: Session, subject: str, user: User | None = None, limit: int = 30, include_ads: bool = True) -> list[dict]:
    """Candidates for «l:<listing id>» / «p:<object id>», the likeliest first: [{kind, property_id, listing_id, where,
    level same|maybe, reasons, decided, address, …, photos, url, can_open}]. A pair marked «Не дубль» is left out."""
    kind, _, ident = subject.partition(":")
    competitors = set(db.scalars(P.competitor_sources()))
    objs = _objects(db)
    # an agent's number (or a landlord's with many flats): behind 3+ objects it names no flat (eval 11-17)
    seen: dict[str, set] = {}
    for o in objs:
        for x in o["phones"]:
            seen.setdefault(_digits(x)[-9:], set()).add(o["key"])
    many = {k for k, v in seen.items() if len(v) >= 3}
    for o in objs:
        o["phones"] = [x for x in o["phones"] if _digits(x)[-9:] not in many]
    if kind == "p":
        s = next((o for o in objs if o["property_id"] == int(ident)), None)
        if s is None:
            raise DomainError("not_found", "object not found")
        skip = {s["key"]} | {key("l", x) for x in s["ad_ids"]}
    elif kind == "l":
        l = db.get(Listing, ident)
        if l is None:
            raise DomainError("not_found", "listing not found")
        s = _listing_profile(l, competitors)
        owner = db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == l.id)) \
            or db.scalar(select(Property.id).where(Property.listing_id == l.id))
        skip = {s["key"]} | ({key("p", owner)} if owner else set())
        if l.source == "object" and l.id.startswith("obj") and l.id[3:].isdigit():
            skip.add(key("p", int(l.id[3:])))
    else:
        raise DomainError("not_found", "bad subject")
    cands = [o for o in objs if o["key"] not in skip]
    ads, ad_idx = _ads(db, competitors) if include_ads else ([], {})
    linked = {key("l", x) for x in db.scalars(select(PropertyListing.listing_id))} if ads else set()
    # a linked ad is its object's: never listed on its own (the cache may predate the link)
    keep = [n for n, a in enumerate(ads) if a["key"] not in skip and a["key"] not in linked]
    shared = {}
    if s["hashes"]:
        obj_idx, base = _photo_index(cands), len(cands)
        hits_o, hits_a = set(), set()
        for h in s["hashes"]:
            for i in range(5):
                k = (i, (h >> (i * 13)) & 0x1FFF)
                hits_o |= obj_idx.get(k, set())
                hits_a |= ad_idx.get(k, set())
        shared = {n: _shared(s["hashes"], cands[n]["hashes"]) for n in hits_o}
        pos = {n: i for i, n in enumerate(keep)}
        shared.update({base + pos[n]: _shared(s["hashes"], ads[n]["hashes"]) for n in hits_a if n in pos})
    cands += [ads[n] for n in keep]
    decided = _decisions(db, s["key"])
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_({d["by"] for d in decided.values() if d["by"]}))).all()) if decided else {}
    out = []
    for n, c in enumerate(cands):
        d = decided.get(c["key"])
        if d and d["verdict"] == "different":
            continue
        level, score, why = compare(s, c, shared.get(n, 0))
        if d and d["verdict"] == "same":
            level, score = "same", score + 100
            why = [f"отмечено как дубль{' · ' + names[d['by']] if names.get(d['by']) else ''}"] + why
        if level is None:
            continue
        item = {**c["out"], "key": c["key"], "level": level, "score": score, "reasons": why,
                "decided": d["verdict"] if d else None}
        if c["kind"] == "object":
            # the card may be closed to him, its photos are not (api media_file, 11-17): he compares by them
            item["can_open"] = user is None or P.can_open(db, db.get(Property, c["property_id"]), user)
        out.append(item)
    out.sort(key=lambda x: (x["level"] != "same", x["kind"] != "object", -x["score"]))
    return out[:limit]


def objects_to_warn(db: Session, listing_id: str, user: User) -> list[dict]:
    """«Беру в работу»: our objects this ad may be (the agent is asked «это другой объект?» before a twin is made).
    None when the ad already is an object's (taking it takes that object, nothing new is made)."""
    if db.scalar(select(Property.id).where(Property.listing_id == listing_id)) is not None \
            or db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == listing_id)) is not None:
        return []
    return [x for x in find(db, key("l", listing_id), user, limit=10, include_ads=False) if x["kind"] == "object"]


def decide(db: Session, a: str, b: str, same: bool, actor: User) -> dict:
    """«Дубль» / «Не дубль» on a pair. An ad called the same as an object is linked to it (matching.attach); two objects
    or two ads stay as they are, the pair is marked (an operator archives the twin: «В архив → Дубль»)."""
    if a == b or not all(re.fullmatch(r"[lp]:[\w.\-:]+", x or "") for x in (a, b)):
        raise DomainError("bad_request", "bad pair")
    x, y = _pair(a, b)
    for k in (x, y):
        kind, _, ident = k.partition(":")
        if (db.get(Property, int(ident)) if kind == "p" and ident.isdigit() else db.get(Listing, ident) if kind == "l" else None) is None:
            raise DomainError("not_found", f"{k} not found")
    d = db.scalar(select(SimilarDecision).where(SimilarDecision.a == x, SimilarDecision.b == y).with_for_update())
    if d is None:
        d = SimilarDecision(a=x, b=y)
        db.add(d)
    d.verdict, d.decided_by, d.decided_at = ("same" if same else "different"), actor.id, now()
    linked = None
    if same and {x[0], y[0]} == {"l", "p"}:
        lk, pk = (x, y) if x.startswith("l") else (y, x)
        l, p = db.get(Listing, lk[2:]), db.get(Property, int(pk[2:]))
        if db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == l.id)) is None \
                and db.scalar(select(Property.id).where(Property.listing_id == l.id)) is None:
            from app.services import matching
            alerts = matching.attach(db, p, l, actor, ["отмечено как дубль"], "agent")
            linked = p.id
        else:
            alerts = []
    else:
        alerts = []
    for k, other in ((x, y), (y, x)):
        if k.startswith("p:"):
            log_event(db, "property", int(k[2:]), "similar_same" if same else "similar_different", actor, other=other)
    db.commit()
    if alerts:
        from app.services import matching
        matching._send(alerts)
    return {"ok": True, "verdict": d.verdict, "linked_to": linked}


def mark_different(db: Session, subject: str, others: list[str], actor: User) -> None:
    """«Это другой объект — беру»: every object shown to him is recorded as not this one. No commit."""
    for o in others:
        x, y = _pair(subject, o)
        d = db.scalar(select(SimilarDecision).where(SimilarDecision.a == x, SimilarDecision.b == y))
        if d is None:
            db.add(SimilarDecision(a=x, b=y, verdict="different", decided_by=actor.id, decided_at=now()))
