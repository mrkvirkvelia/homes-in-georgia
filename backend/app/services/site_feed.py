"""Public read-only feed for the agency site hge.ge (served by app/api/site.py, no login).

The item shape is the site's own listings.json item (the site was built on it): empty values are left out, like the old
builder did. STRICT whitelist: an item is built key by key from the object's public fields; nothing is copied wholesale
(no owner / tenant / lease / cadastral / checklist / ai_flags / archive / review fields, no private media)."""
import time

import httpx
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Property, PropertyMedia, User
from app.services import properties as P

NBG_URL = "https://nbg.gov.ge/gw/api/ct/monetarypolicy/currencies/en/json/?currencies=USD&currencies=EUR"
FALLBACK_RATES = {"USD": 1.0, "GEL": round(1 / 2.7, 6), "EUR": 1.08}
RATES_TTL, FEED_TTL = 12 * 3600, 60
DEFAULT_AGENT = {"telegram": "David_Tibelashvili", "phone": "+995 599 20 67 16"}
PHOTO_URL = "/api/public/site/photos/{pid}/{n}"

# CRM post_fields tag <-> the site's word (the importer writes the tags, the feed reads them back)
KIND = {"apartment": "Apartment", "house": "House", "commercial": "Commercial", "land": "Land"}
BUILDING = {"new": "NewBuilding", "old": "OldBuilding", "historical": "HistoricalBuilding"}
HEATING = {"central": "CentralHeating", "gas": "GasHeating", "electric": "ElectricalHeating"}
PETS = {"allowed": "Allowed", "no": "NotAllowed", "agreement": "ByAgreement"}
FRAME = {"white_frame": "WhiteFrame", "green_frame": "GreenFrame", "black_frame": "BlackFrame"}
DESIGN = {"renovated": "New", "mixed": "Mixed", "old": "Old"}
AMENITY = {"balcony": "Balcony", "terrace": "Terrace", "courtyard": "Courtyard", "wifi": "WiFi", "tv": "TV",
           "dishwasher": "Dishwasher", "stove": "Stove", "microwave": "Microwave", "washer": "WashingMachine",
           "vacuum": "VacuumCleaner", "fireplace": "Fireplace", "elevator": "Elevator", "oven": "Oven",
           "parking": "ParkingPlace", "conditioner": "Conditioner", "bath": "Bath", "shower": "Shower"}
METRO = {"Liberty Square": "LibertySquare", "Rustaveli": "Rustaveli", "Marjanishvili": "Marjanishvili",
         "Station Square": "StationSquare", "Tsereteli": "Tsereteli", "Gotsiridze": "Gotsiridze",
         "Nadzaladevi": "Nadzaladevi", "Didube": "Didube", "Grmagele": "Grmagele", "Guramishvili": "Guramishvili",
         "Sarajishvili": "Sarajishvili", "Akhmeteli Theatre": "AhmeteliTheatre", "Technical University": "STUniversity",
         "Vazha-Pshavela": "VazhaPshavela", "Delisi": "Delisi", "State University": "TCUniversity",
         "Medical University": "MCUniversity", "Avlabari": "AvlabariMetro", "Isani": "IsaniMetro",
         "300 Aragveli": "300Aragveli", "Samgori": "SamgoriMetro", "Varketili": "Varketili"}


def inv(d: dict) -> dict:
    return {v: k for k, v in d.items()}


def _clear(v) -> bool:
    return v in (None, "", [], False)  # the old builder's rule (0 is dropped too)


# ---------------------------------------------------------------- rates (NBG, 12 h)

_rates = {"at": 0.0, "v": dict(FALLBACK_RATES)}


def parse_nbg(payload) -> dict:
    day = payload[0] if isinstance(payload, list) else payload
    cur = day.get("currencies") if isinstance(day, dict) and "currencies" in day else payload
    gel_per = {c["code"]: float(c["rate"]) / float(c.get("quantity") or 1) for c in cur}
    usd = gel_per["USD"]
    return {"USD": 1.0, "GEL": round(1 / usd, 6), "EUR": round(gel_per["EUR"] / usd, 6)}


def rates() -> dict:
    if time.time() - _rates["at"] > RATES_TTL:
        _rates["at"] = time.time()  # also after a failure: no hammering the bank, the old / fallback rates stay
        try:
            # without &date= the bank answers [] on some days (14.11.2026, a Saturday); with today's date it never does
            day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 4 * 3600))  # Tbilisi date
            r = httpx.get(f"{NBG_URL}&date={day}", timeout=8, headers={"User-Agent": "HomesInGeorgiaSite/1.0"})
            r.raise_for_status()
            _rates["v"] = parse_nbg(r.json())
        except Exception:  # network or format problem
            pass
    return _rates["v"]


# ---------------------------------------------------------------- items

def _agent(u: User | None) -> dict:
    return {"telegram": (u.username if u and u.username else DEFAULT_AGENT["telegram"]).lstrip("@"),
            "phone": (u.phone if u and u.phone else DEFAULT_AGENT["phone"])}


def item(p: Property, n_photos: int, agent: User | None, fx: dict) -> dict:
    f = p.post_fields or {}
    extra = f.get("site_extra") or {}
    service = f.get("service") or "rent"
    car = f.get("car") or {}
    is_car = service.startswith("car")
    price = float(p.price) if p.price is not None else None
    price_usd = round(price * fx.get(p.currency or "USD", 1)) if price else None
    area = float(p.area) if p.area is not None else None
    sale = f.get("deal") == "Sale"
    cond = next((k for k, v in FRAME.items() if v == f.get("condition")), None) or \
        ("renovated" if f.get("condition") == "FullyRenovated" else None) or \
        inv(DESIGN).get(f.get("design"), "old" if f.get("design") else None) or extra.get("condition")
    months = f.get("months") or [int(x[:-5]) for x in f.get("periods") or [] if x.endswith("Month")]
    amenities = [inv(AMENITY).get(a, a.lower()) for a in f.get("amenities") or []] + (extra.get("amenities") or [])
    d = {
        "id": f"o{p.id}", "legacy_id": f.get("site_id"), "service": service,
        "source": f.get("site_source") or service, "deal": "sale" if sale else "rent", "period": f.get("period"),
        "kind": "car" if is_car else inv(KIND).get(f.get("prop_type"), "apartment" if not f.get("prop_type") else "commercial"),
        "title": (car.get("title") or "Car") if is_car else p.address,
        "headline": f.get("headline"), "district": None if is_car else p.district,
        "metro": None if is_car else (inv(METRO).get(f.get("metro")) or extra.get("metro")),
        "lat": p.lat, "lon": p.lng, "approx": f.get("approx"),
        "price": price, "currency": p.currency, "price_usd": price_usd, "deposit": f.get("deposit"),
        "ppsqm_usd": (round(price_usd / area) if price_usd and area else f.get("ppsqm_usd")) if sale and not is_car else None,
        "rooms": p.bedrooms, "area": area, "floor": p.floor, "floors": p.total_floors,
        "building": inv(BUILDING).get(f.get("building")) or extra.get("building"), "condition": cond,
        "heating": inv(HEATING).get(f.get("heating")) or extra.get("heating"), "amenities": amenities,
        "year": car.get("year"), "gearbox": car.get("gearbox"), "fuel": car.get("fuel"), "body": car.get("body"),
        "seats": car.get("seats"), "mileage": car.get("mileage"), "pickup": p.address if is_car else None,
        "pets": inv(PETS).get(f.get("pets")), "months": months, "tenants": f.get("tenants"),
        "exclusive": p.is_exclusive, "completion": f.get("completion"), "description": p.description,
        "agent": _agent(agent), "photos": [PHOTO_URL.format(pid=p.id, n=n) for n in range(n_photos)],
        "post_url": p.post_url, "published_at": p.published_at.isoformat() if p.published_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    return {k: v for k, v in d.items() if not _clear(v)}


def photo_keys(db: Session, pid: int) -> list[str]:
    """Storage keys of the object's public photos, in order (the n of /photos/<pid>/<n>)."""
    return [k for k in db.scalars(select(PropertyMedia.path).where(PropertyMedia.property_id == pid, PropertyMedia.kind == "photo")
                                  .order_by(PropertyMedia.position, PropertyMedia.id)) if not k.startswith(P.PRIVATE_PREFIX)]


def public_filter():
    has_photo = exists().where(PropertyMedia.property_id == Property.id, PropertyMedia.kind == "photo",
                               ~PropertyMedia.path.startswith(P.PRIVATE_PREFIX))
    return (Property.status == "published", has_photo)


def public_property(db: Session, ident: str) -> Property | None:
    """A public object by "o<pid>" or its old site id ("rent-551776"); None when it is not public."""
    q = select(Property).where(*public_filter())
    if ident[:1] == "o" and ident[1:].isdigit():
        q = q.where(Property.id == int(ident[1:]))
    else:
        q = q.where(Property.post_fields["site_id"].astext == ident)
    return db.scalars(q.limit(1)).first()


def feed(db: Session) -> dict:
    rows = db.scalars(select(Property).where(*public_filter()).order_by(Property.published_at.desc().nulls_last(), Property.id.desc())).all()
    counts: dict[int, int] = {}
    for pid, in db.execute(select(PropertyMedia.property_id).where(
            PropertyMedia.kind == "photo", ~PropertyMedia.path.startswith(P.PRIVATE_PREFIX),
            PropertyMedia.property_id.in_([p.id for p in rows]))):
        counts[pid] = counts.get(pid, 0) + 1
    agents = {u.id: u for u in db.scalars(select(User).where(User.id.in_({p.agent_id for p in rows if p.agent_id})))}
    fx = rates()
    items = [item(p, counts.get(p.id, 0), agents.get(p.agent_id), fx) for p in rows]
    by: dict[str, int] = {}
    for i in items:
        by[i["service"]] = by.get(i["service"], 0) + 1
    return {"updated_at": max((i["updated_at"] for i in items if "updated_at" in i), default=None),
            "rates_usd": fx, "counts": by, "items": items}


_cache = {"at": 0.0, "v": None}


def cached_feed(db: Session) -> dict:
    # ponytail: per process, 60 s; add a shared cache only if the API ever runs many workers
    if _cache["v"] is None or time.time() - _cache["at"] > FEED_TTL:
        _cache["v"], _cache["at"] = feed(db), time.time()
    return _cache["v"]


def clear_cache() -> None:
    _cache["v"] = None


def detail(db: Session, ident: str) -> dict | None:
    p = public_property(db, ident)
    if p is None:
        return None
    d = item(p, len(photo_keys(db, p.id)), db.get(User, p.agent_id) if p.agent_id else None, rates())
    if db.scalar(select(PropertyMedia.id).where(PropertyMedia.property_id == p.id, PropertyMedia.kind == "video",
                                                ~PropertyMedia.path.startswith(P.PRIVATE_PREFIX))):
        d["video"] = f"/api/public/site/video/{p.id}"
    else:
        d["video"] = None
    return d
