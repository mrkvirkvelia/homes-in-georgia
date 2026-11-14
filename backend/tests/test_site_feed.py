"""Site catalog importer + the public feed for hge.ge (importers/site_catalog.py, services/site_feed.py, api/site.py)."""
import io
import json

import pytest
from PIL import Image

from app.importers import site_catalog as imp
from app.models import Owner, Property, PropertyMedia, PropertyPublication
from app.services import catalog, site_feed
from tests.conftest import make_user

AGENT = {"telegram": "David_Tibelashvili", "phone": "+995 599 20 67 16"}
RENT = {"id": "rent-551776", "service": "rent", "source": "rent", "deal": "rent", "period": "month", "kind": "apartment",
        "title": "5 Chavchavadze Ave", "headline": "Cozy", "district": "Vake", "metro": "Rustaveli", "lat": 41.7, "lon": 44.7,
        "price": 800.0, "currency": "USD", "price_usd": 800, "deposit": 800.0, "rooms": 2, "area": 60.0, "floor": 3,
        "floors": 9, "building": "new", "condition": "renovated", "heating": "central",
        "amenities": ["conditioner", "washer", "parking", "pool"], "pets": "agreement", "months": [6, 12, 24],
        "tenants": 3, "exclusive": True, "description": "Nice flat", "agent": AGENT, "photos": ["media/rent/1.jpg", "media/rent/2.jpg"],
        "post_url": "https://t.me/rent_tbilisi_ge/551776", "published_at": "2026-11-14T12:15:26+04:00"}
SALE = {"id": "sale-77", "service": "sale", "source": "sale", "deal": "sale", "kind": "apartment", "title": "1 Sale St",
        "district": "Saburtalo", "price": 100000.0, "currency": "USD", "price_usd": 100000, "rooms": 2, "area": 50.0,
        "condition": "white_frame", "description": "Sale", "agent": AGENT, "photos": ["media/sale/77-1.jpg"],
        "post_url": "https://t.me/sale_in_tbilisi/77", "published_at": "2026-11-13T10:00:00+04:00"}
CAR = {"id": "car-rent-9", "service": "car-rent", "source": "car-rent", "deal": "rent", "period": "day", "kind": "car",
       "title": "Jeep Compass", "price": 60.0, "currency": "USD", "price_usd": 60, "year": 2022, "gearbox": "auto",
       "fuel": "petrol", "body": "suv", "seats": 5, "pickup": "8 Arakishvili St", "description": "car", "agent": AGENT,
       "photos": ["media/car-rent/9-1.jpg"], "post_url": "https://t.me/CarsRentInGeorgia/9",
       "published_at": "2026-11-12T10:00:00+04:00"}
ITEMS = [RENT, SALE, CAR]


@pytest.fixture(autouse=True)
def _feed(monkeypatch):
    site_feed.clear_cache()
    monkeypatch.setattr(site_feed, "rates", lambda: {"USD": 1.0, "GEL": 0.4, "EUR": 1.1})
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
    monkeypatch.setattr(imp, "fetch", lambda path: (".jpg", buf.getvalue()))
    yield
    site_feed.clear_cache()


def run(db, items=ITEMS, **kw):
    return imp.run(db, [dict(i) for i in items], out=lambda *_: None, **kw)


def by_site(db, sid):
    return db.query(Property).filter(Property.post_fields["site_id"].astext == sid).one()


def test_import_creates_and_is_idempotent(db):
    r = run(db)
    assert sum(r["created"].values()) == 3 and r["photos"] == {"rent": 2, "sale": 1, "car-rent": 1}
    p = by_site(db, "rent-551776")
    assert (p.address, p.bedrooms, p.floor, p.total_floors, p.status, p.owner_id, p.is_exclusive) == (
        "5 Chavchavadze Ave", 2, 3, 9, "published", None, True)
    assert p.post_message_id == "551776" and p.post_fields["service"] == "rent" and p.post_fields["deal"] == "Rent"
    assert p.post_fields["heating"] == "CentralHeating" and p.post_fields["site_extra"] == {"amenities": ["pool"]}
    assert db.query(PropertyPublication).filter_by(property_id=p.id, url=RENT["post_url"]).count() == 1
    car = by_site(db, "car-rent-9")
    assert car.address == "8 Arakishvili St" and car.post_fields["car"]["year"] == 2022
    r2 = run(db)
    assert sum(r2["created"].values()) == 0 and sum(r2["matched"].values()) == 3 and sum(r2["photos"].values()) == 0
    assert db.query(Property).count() == 3 and db.query(PropertyMedia).count() == 4


def test_dry_run_writes_nothing(db):
    run(db, dry_run=True)
    assert db.query(Property).count() == 0


def test_dedupe_by_post_url_keeps_existing_fields(db):
    agent = make_user(db, "agent", username="zaza", phone="+995 555 1")
    old = Property(post_url=RENT["post_url"], status="published", address="My own address", price=900, agent_id=agent.id,
                   post_fields={"heating": "GasHeating"})
    db.add(old)
    db.commit()
    r = run(db, [RENT])
    assert r["matched"] == {"rent": 1} and r["created"] == {}
    db.expire_all()
    p = db.get(Property, old.id)
    assert (p.address, float(p.price), p.agent_id) == ("My own address", 900, agent.id)
    assert p.post_fields == {"heating": "GasHeating", "service": "rent", "site_id": "rent-551776", "deal": "Rent"}
    assert p.district == "Vake" and p.area is not None  # empty columns filled
    assert db.query(Property).count() == 1 and db.query(PropertyMedia).count() == 2  # it had no photos


def test_feed_only_public(db, client):
    run(db)
    pa = by_site(db, "sale-77")
    pa.status = "archived"
    db.add(Property(status="published", address="No photo"))
    db.commit()
    site_feed.clear_cache()
    d = client.get("/api/public/site/listings").json()
    assert d["counts"] == {"rent": 1, "car-rent": 1} and len(d["items"]) == 2
    assert d["rates_usd"]["GEL"] == 0.4
    assert [i["service"] for i in d["items"]] == ["rent", "car-rent"]  # published_at desc
    rent = d["items"][0]
    assert rent["legacy_id"] == "rent-551776" and rent["id"].startswith("o")
    assert rent["photos"] == [f"/api/public/site/photos/{rent['id'][1:]}/0", f"/api/public/site/photos/{rent['id'][1:]}/1"]
    assert rent["metro"] == "Rustaveli" and rent["heating"] == "central" and rent["building"] == "new"
    assert rent["condition"] == "renovated" and rent["pets"] == "agreement" and rent["months"] == [6, 12, 24]
    assert rent["amenities"] == ["conditioner", "washer", "parking", "pool"] and rent["agent"] == AGENT
    assert rent["price_usd"] == 800 and rent["kind"] == "apartment" and rent["exclusive"] is True
    car = d["items"][1]
    assert car["title"] == "Jeep Compass" and car["pickup"] == "8 Arakishvili St" and car["seats"] == 5 and car["kind"] == "car"
    assert client.get("/api/public/site/listings").headers["cache-control"] == "public, max-age=60"


def test_sale_ppsqm_and_catalog_hidden(db, client):
    run(db)
    p = by_site(db, "sale-77")
    item = next(i for i in client.get("/api/public/site/listings").json()["items"] if i["service"] == "sale")
    assert item["ppsqm_usd"] == 2000 and item["condition"] == "white_frame" and item["deal"] == "sale"
    assert p.post_message_id and not catalog.visible(p)
    assert catalog.visible(Property(status="published", post_url="u", post_message_id="1", post_fields={"service": "rent"}))
    assert catalog.visible(Property(status="published", post_url="u", post_message_id="1", post_fields={}))


def test_no_private_data(db, client):
    agent = make_user(db, "agent", username="zaza", phone="+995 555 11 22 33")
    owner = Owner(name="SECRETOWNER", phone="+995 599 77 77 77", phone_norm="599777777")
    db.add(owner)
    db.flush()
    run(db, [RENT])
    p = by_site(db, "rent-551776")
    p.owner_id, p.agent_id = owner.id, agent.id
    p.tenant_name, p.tenant_phone, p.cadastral_code = "SECRETTENANT", "+995 500 00 00 01", "01.14.12.003.045"
    p.source_url, p.review_comment, p.archive_comment = "https://secret.example/src", "SECRETREVIEW", "SECRETARCH"
    p.checklist, p.ai_flags = {"x": "SECRETCHECK"}, {"y": "SECRETFLAG"}
    db.add(PropertyMedia(property_id=p.id, kind="owner_id_doc", path="private/properties/1/id.jpg", position=0))
    db.add(PropertyMedia(property_id=p.id, kind="photo", path="private/x.jpg", position=0))
    db.commit()
    site_feed.clear_cache()
    pid = p.id
    blob = client.get("/api/public/site/listings").text + client.get(f"/api/public/site/listings/o{pid}").text
    for bad in ("SECRET", "599777777", "599 77 77", "500 00 00", "01.14.12", "tenant_", "owner", "cadastral", "checklist",
                "ai_flags", "review_comment", "archive", "source_url", "private/", "properties/"):
        assert bad.lower() not in blob.lower(), bad
    assert json.loads(client.get("/api/public/site/listings").text)["items"][0]["agent"] == {
        "telegram": "zaza", "phone": "+995 555 11 22 33"}
    assert len(client.get(f"/api/public/site/listings/o{pid}").json()["photos"]) == 2  # the private one is not counted
    assert client.get(f"/api/public/site/photos/{pid}/2").status_code == 404


def test_detail_legacy_id_and_photos(db, client):
    run(db)
    p = by_site(db, "rent-551776")
    d = client.get("/api/public/site/listings/rent-551776")
    assert d.status_code == 200 and d.json()["id"] == f"o{p.id}" and d.json()["video"] is None
    assert client.get(f"/api/public/site/listings/o{p.id}").json()["description"] == "Nice flat"
    assert client.get("/api/public/site/listings/nope").status_code == 404
    r = client.get(f"/api/public/site/photos/{p.id}/0")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=86400"
    r = client.get(f"/api/public/site/photos/{p.id}/0?p=1")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert client.get(f"/api/public/site/photos/{p.id}/5").status_code == 404
    p.status = "rented"
    db.commit()
    assert client.get("/api/public/site/listings/rent-551776").status_code == 404
    assert client.get(f"/api/public/site/photos/{p.id}/0").status_code == 404
