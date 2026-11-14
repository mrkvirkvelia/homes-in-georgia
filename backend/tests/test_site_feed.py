"""The public feed (services/site_feed.py, api/site.py) and the CRM
screens' API for sale objects and cars (api/offers.py)."""
import io
import json

import pytest
from PIL import Image

from tests import hge_import as imp
from app.models import Car, Owner, Property, PropertyMedia, PropertyPublication, SaleObject
from app.services import catalog, site_feed
from tests.conftest import auth, make_user

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
CAR_SALE = {"id": "car-sale-18", "service": "car-sale", "source": "car-sale", "deal": "sale", "kind": "car", "title": "Corvette",
            "price": 30000.0, "currency": "USD", "price_usd": 30000, "year": 2014, "mileage": 76538.0, "fuel": "petrol",
            "exclusive": True, "agent": AGENT, "photos": ["media/car-sale/18-1.jpg"], "post_url": "https://t.me/CarsSale/18",
            "published_at": "2026-11-11T10:00:00+04:00"}
NEW = {"id": "new-5", "service": "new", "source": "new", "deal": "sale", "kind": "apartment", "title": "3 New Tower",
       "district": "Vake", "metro": "Rustaveli", "price": 90000.0, "currency": "USD", "price_usd": 90000, "area": 45.0,
       "building": "new", "completion": "Q4 2027", "amenities": ["balcony", "pool"], "agent": AGENT,
       "photos": ["media/new/5-1.jpg"], "published_at": "2026-11-10T10:00:00+04:00"}
COMM_SALE = {"id": "commercial-3", "service": "commercial", "source": "commercial", "deal": "sale", "kind": "commercial",
             "title": "Shop", "price": 200000.0, "currency": "USD", "area": 100.0, "agent": AGENT, "photos": ["media/c/3.jpg"]}
COMM_RENT = {"id": "commercial-4", "service": "commercial", "source": "commercial", "deal": "rent", "period": "month",
             "kind": "commercial", "title": "Office", "price": 1000.0, "currency": "USD", "area": 80.0, "agent": AGENT,
             "photos": ["media/c/4.jpg"]}


@pytest.fixture(autouse=True)
def _feed(monkeypatch):
    site_feed.clear_cache()
    monkeypatch.setattr(site_feed, "rates", lambda: {"USD": 1.0, "GEL": 0.4, "EUR": 1.1})
    monkeypatch.setattr(imp, "fetch", lambda path: (".jpg", jpg()))
    yield
    site_feed.clear_cache()


def jpg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
    return buf.getvalue()


def run(db, items=ITEMS, **kw):
    return imp.run(db, [dict(i) for i in items], **kw)


def by_site(db, sid):
    return db.query(Property).filter(Property.post_fields["site_id"].astext == sid).one()


def sale(db, sid):
    return db.query(SaleObject).filter_by(site_id=sid).one()


def test_feed_only_public_three_sources(db, client):
    run(db, [*ITEMS, NEW, CAR_SALE])
    sale(db, "new-5").status = "archived"
    db.add(Property(status="published", address="No photo"))
    db.add(SaleObject(service="sale", title="Draft", status="draft", photos=["offers/s1/x.jpg"]))
    db.add(Car(deal="rent", title="No photo", status="published"))
    db.commit()
    site_feed.clear_cache()
    d = client.get("/api/public/site/listings").json()
    assert d["counts"] == {"rent": 1, "sale": 1, "car-rent": 1, "car-sale": 1} and len(d["items"]) == 4
    assert d["rates_usd"]["GEL"] == 0.4
    assert [i["service"] for i in d["items"]] == ["rent", "sale", "car-rent", "car-sale"]  # published_at desc
    rent, sl, car, cs = d["items"]
    assert rent["legacy_id"] == "rent-551776" and rent["id"].startswith("o") and rent["deal"] == "rent"
    pid = rent["id"][1:]
    assert rent["photos"] == [f"/api/public/site/photos/o{pid}/0", f"/api/public/site/photos/o{pid}/1"]
    assert rent["metro"] == "Rustaveli" and rent["heating"] == "central" and rent["building"] == "new"
    assert rent["condition"] == "renovated" and rent["pets"] == "agreement" and rent["months"] == [6, 12, 24]
    assert rent["amenities"] == ["conditioner", "washer", "parking", "pool"] and rent["agent"] == AGENT
    assert rent["price_usd"] == 800 and rent["kind"] == "apartment" and rent["exclusive"] is True
    assert sl["id"].startswith("s") and sl["legacy_id"] == "sale-77" and sl["deal"] == "sale" and sl["ppsqm_usd"] == 2000
    assert sl["condition"] == "white_frame" and sl["photos"] == [f"/api/public/site/photos/{sl['id']}/0"]
    assert car["id"].startswith("c") and car["title"] == "Jeep Compass" and car["pickup"] == "8 Arakishvili St"
    assert car["seats"] == 5 and car["kind"] == "car" and car["period"] == "day" and car["deal"] == "rent"
    assert cs["deal"] == "sale" and cs["mileage"] == 76538 and cs["exclusive"] is True and "period" not in cs
    assert client.get("/api/public/site/listings").headers["cache-control"] == "public, max-age=60"


def test_sale_hidden_from_bot_catalog(db):
    run(db)
    p = by_site(db, "rent-551776")
    assert catalog.visible(p)  # a rent object with its post stays in the catalog
    p.post_fields = {**p.post_fields, "service": "daily"}
    assert not catalog.visible(p)
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
                "ai_flags", "review_comment", "archive", "source_url", "private/", "properties/", "offers/"):
        assert bad.lower() not in blob.lower(), bad
    assert json.loads(client.get("/api/public/site/listings").text)["items"][0]["agent"] == {
        "telegram": "zaza", "phone": "+995 555 11 22 33"}
    assert len(client.get(f"/api/public/site/listings/o{pid}").json()["photos"]) == 2  # the private one is not counted
    assert client.get(f"/api/public/site/photos/o{pid}/2").status_code == 404


def test_detail_legacy_ids_and_photos(db, client):
    run(db, [*ITEMS, NEW])
    p, s, c = by_site(db, "rent-551776"), sale(db, "new-5"), db.query(Car).one()
    d = client.get("/api/public/site/listings/rent-551776")
    assert d.status_code == 200 and d.json()["id"] == f"o{p.id}" and d.json()["video"] is None
    assert client.get("/api/public/site/listings/sale-77").json()["id"].startswith("s")
    assert client.get("/api/public/site/listings/car-rent-9").json()["id"] == f"c{c.id}"
    assert client.get(f"/api/public/site/listings/s{s.id}").json()["completion"] == "Q4 2027"
    assert client.get(f"/api/public/site/listings/o{p.id}").json()["description"] == "Nice flat"
    assert client.get("/api/public/site/listings/nope").status_code == 404
    for ident, n in ((f"o{p.id}", 2), (f"s{s.id}", 1), (f"c{c.id}", 1)):
        r = client.get(f"/api/public/site/photos/{ident}/0")
        assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=86400"
        assert client.get(f"/api/public/site/photos/{ident}/0?p=1").headers["content-type"] == "image/webp"
        assert client.get(f"/api/public/site/photos/{ident}/{n}").status_code == 404
    assert client.get(f"/api/public/site/photos/{p.id}/0").status_code == 404  # the bare number is no longer an id
    p.status = "rented"
    db.commit()
    assert client.get("/api/public/site/listings/rent-551776").status_code == 404
    assert client.get(f"/api/public/site/photos/o{p.id}/0").status_code == 404


# ---------------------------------------------------------------- CRM API

def up(client, h, kind, oid, n=1, name="a.jpg"):
    return client.post(f"/api/offers/{kind}/{oid}/media", headers=h, files=[("files", (name, jpg(), "image/jpeg"))] * n)


def test_crm_sale_flow_to_the_site(db, client):
    agent = make_user(db, "agent", username="zaza", phone="+995 555 11 22 33")
    h = auth(agent)
    r = client.post("/api/offers/sale", headers=h, json={"service": "new", "title": "9 Test St", "price": 100000, "area": 50,
                                                          "kind": "apartment", "building": "new", "completion": "2027",
                                                          "amenities": ["balcony"], "district": "Vake"})
    assert r.status_code == 200, r.text
    o = r.json()
    oid = o["id"]
    assert o["status"] == "draft" and o["agent_id"] == agent.id and o["item_id"] == f"s{oid}" and o["public"] is False
    assert client.post(f"/api/offers/sale/{oid}/status", headers=h, json={"status": "published"}).status_code == 400  # no photo
    r = up(client, h, "sale", oid, 2)
    assert r.status_code == 200 and len(r.json()["photos"]) == 2 and len(r.json()["uploaded_keys"]) == 2
    r = client.post(f"/api/offers/sale/{oid}/status", headers=h, json={"status": "published"})
    assert r.status_code == 200 and r.json()["published_at"] and r.json()["public"] is True
    d = client.get("/api/public/site/listings").json()  # cache cleared by the CRM call, no waiting
    it = d["items"][0]
    assert d["counts"] == {"new": 1} and it["id"] == f"s{oid}" and it["agent"]["telegram"] == "zaza"
    assert it["photos"] == [f"/api/public/site/photos/s{oid}/0", f"/api/public/site/photos/s{oid}/1"] and it["ppsqm_usd"] == 2000
    assert client.get(f"/api/public/site/photos/s{oid}/1?p=1").status_code == 200
    # edit shows up at once; the private fields of the row never do
    assert client.patch(f"/api/offers/sale/{oid}", headers=h, json={"price": 120000}).json()["price"] == 120000
    assert client.get("/api/public/site/listings").json()["items"][0]["price"] == 120000
    assert "agent_id" not in json.dumps(client.get(f"/api/public/site/listings/s{oid}").json())
    # reorder + delete a photo
    k0, k1 = r.json()["photos"]
    assert client.put(f"/api/offers/sale/{oid}/media/order", headers=h, json={"keys": [k1, k0]}).json()["photos"] == [k1, k0]
    assert client.put(f"/api/offers/sale/{oid}/media/order", headers=h, json={"keys": [k1]}).status_code == 409
    r = client.delete(f"/api/offers/sale/{oid}/media", headers=h, params={"key": k1})
    assert r.json()["photos"] == [k0]
    assert client.delete(f"/api/offers/sale/{oid}/media", headers=h, params={"key": k1}).status_code == 404
    # unpublish: gone; the last photo gone: cannot publish again
    assert client.post(f"/api/offers/sale/{oid}/status", headers=h, json={"status": "draft"}).json()["status"] == "draft"
    assert client.get("/api/public/site/listings").json()["items"] == []
    assert client.get(f"/api/public/site/listings/s{oid}").status_code == 404
    assert client.get("/api/offers/sale", headers=h, params={"status": "draft"}).json()["total"] == 1
    assert client.get("/api/offers/sale", headers=h, params={"status": "published"}).json()["total"] == 0


def test_crm_car_and_validation(db, client):
    agent = make_user(db, "agent")
    h = auth(agent)
    assert client.post("/api/offers/car", headers=h, json={"title": "X"}).status_code == 422  # no deal
    assert client.post("/api/offers/car", headers=h, json={"deal": "lease", "title": "X"}).status_code == 422
    assert client.post("/api/offers/sale", headers=h, json={"service": "sale", "title": "A", "heating": "lava"}).status_code == 422
    r = client.post("/api/offers/car", headers=h, json={"deal": "rent", "title": "Kia Rio", "price": 40, "period": "day",
                                                         "year": 2020, "gearbox": "auto", "pickup": "Airport"})
    cid = r.json()["id"]
    assert up(client, h, "car", cid, 10).status_code == 422  # max 9 photos
    assert client.post(f"/api/offers/car/{cid}/media", headers=h, files=[("files", ("a.exe", b"x", "x/y"))]).status_code == 400
    assert up(client, h, "car", cid).status_code == 200
    r = client.post(f"/api/offers/car/{cid}/media", headers=h, files=[("files", ("v.mp4", b"vid", "video/mp4"))])
    assert r.status_code == 200 and r.json()["video"].endswith(".mp4")
    assert client.post(f"/api/offers/car/{cid}/status", headers=h, json={"status": "published"}).status_code == 200
    it = client.get(f"/api/public/site/listings/c{cid}").json()
    assert it["service"] == "car-rent" and it["video"] == f"/api/public/site/video/c{cid}" and it["pickup"] == "Airport"
    assert client.get(f"/api/public/site/video/c{cid}").status_code == 200
    assert client.get("/api/public/site/video/c999").status_code == 404


def test_crm_access(db, client):
    assert client.get("/api/offers/sale").status_code == 401
    for role, code in (("recruit", 403), ("daily_rent_manager", 403), ("agent", 200), ("operator", 200), ("admin", 200)):
        assert client.get("/api/offers/sale", headers=auth(make_user(db, role))).status_code == code, role
    a = make_user(db, "agent")
    b = make_user(db, "operator")
    o = client.post("/api/offers/sale", headers=auth(a), json={"service": "sale", "title": "A", "agent_id": b.id}).json()
    assert o["agent_id"] == a.id  # an agent cannot hand it to somebody else
    assert client.patch(f"/api/offers/sale/{o['id']}", headers=auth(b), json={"agent_id": b.id}).json()["agent_id"] == b.id
