"""Копии объекта на myhome (services/myhome_copies.py, David 11-22): the search keeps the object's district / street and
floor ±1; the ads become «copy» listings (a live parser ad untouched) and «Похожие» shows a copy with the object's photos.
No network: search() and the photo download are faked."""
import json

from app.models import Listing
from app.services import myhome_copies as M
from app.services import similar
from tests.conftest import make_listing, make_user
from tests.test_similar import H, _object


def ad(i, **kw):
    return {"id": i, "address": "რამიშვილი ნ. ქ. ", "area": 56, "floor": 8, "bedroom": "1", "room": "2", "urban_name": "Vake",
            "urban_id": 38, "street_id": 1212, "price": {"2": {"price_total": 800}}, "comment": "ქირავდება<br />ბინა",
            "images": [{"large": f"https://img/{i}/{n}.webp"} for n in range(3)], "dynamic_slug": "x", **kw}


def test_candidates_keep_district_street_and_floor(monkeypatch):
    from types import SimpleNamespace as N
    calls = []

    def fake(query, pause=1.0):
        calls.append(query)
        if query.startswith("streets="):
            return [ad(3), ad(4, floor=2)]
        return [ad(1), ad(2, urban_name="Saburtalo", urban_id=47, street_id=9, address="Kazbegi 3")]
    monkeypatch.setattr(M, "search", fake)
    p = N(id=1, rooms=None, bedrooms=1, area=57.0, floor=8, district="Ваке", address="Ramishvili 3")
    got = sorted(i["id"] for i in M.candidates(p, pause=0))
    assert got == [1, 3]  # #2 another district and street, #4 the 2nd floor
    assert calls[0] == "room_types=2&area_from=50&area_to=64" and "urbans=38&" in calls[1] and "streets=1212&" in calls[2]


def test_copies_saved_and_shown_in_similar(db, client, monkeypatch):
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    make_listing(db, "mh5", source="myhome.ge", status="published")  # the parser's own live ad: left alone
    monkeypatch.setattr(M, "_hashes", lambda urls: list(H[:3]))  # the agent re-posted the owner's photos
    assert M.save(db, [ad(7, area=70, floor=4, bedroom="2"), ad(5)]) == 1  # the object: 70 m², 4th floor, 2 bedrooms
    l = db.get(Listing, "mh7")
    assert l.status == "copy" and l.district == "Ваке" and l.price_usd == 800 and l.text == "ქირავდება\nბინა"
    assert db.get(Listing, "mh5").status == "published"
    res = similar.find(db, f"p:{pid}", vika)
    x = next((c for c in res if c["key"] == "l:mh7"), None)
    assert x is not None and x["level"] in ("same", "maybe") and any("общих фото" in r for r in x["reasons"])


def ss_ad(i, **kw):
    a = {"subdistrictId": 5, "subdistrictTitle": "Vake", "streetId": 77, "streetTitle": "Nino Ramishvili St.", "streetNumber": None}
    return {"applicationId": i, "detailUrl": f"x-{i}", "totalArea": 57, "floorNumber": "8", "numberOfBedrooms": 1,
            "price": {"priceUsd": 800}, "title": "ბინა", "description": "ქირავდება", "address": {**a, **kw.pop("address", {})},
            "appImages": [{"fileName": f"https://ss/{i}/{n}_Thumb.jpg"} for n in range(3)], **kw}


def test_ss_candidates_find_the_district_and_street_ids_then_search_them(monkeypatch):
    from types import SimpleNamespace as N
    calls = []

    def fake(queries, pages=3):
        calls.append(queries)
        if len(calls) == 1:  # the city by the area
            return [ss_ad(1), ss_ad(2, address={"subdistrictId": 9, "subdistrictTitle": "Saburtalo", "streetId": 8,
                                                "streetTitle": "Kazbegi"})]
        return [ss_ad(3, floorNumber="2"), ss_ad(4, numberOfBedrooms=2), ss_ad(5)]
    monkeypatch.setattr(M, "ss_search", fake)
    p = N(id=1, bedrooms=1, area=57.0, floor=8, district="Ваке", address="Ramishvili 3")
    rows = M.ss_candidates(p)
    assert sorted(r["id"] for r in rows) == ["ss1", "ss5"]  # 2: Saburtalo; 3: 2nd floor; 4: 2 bedrooms
    assert calls[1] == [{"areaFrom": 50, "areaTo": 64, "subdistrictIds": [5]}, {"areaFrom": 50, "areaTo": 64, "streetIds": [77]}]
    r = next(r for r in rows if r["id"] == "ss1")
    assert r["photos"][0] == "https://ss/1/0.jpg" and r["floor"] == 8 and r["district"] == "Ваке" and r["source"] == "ss.ge"


def test_compare_by_link(db, client, monkeypatch):
    from tests.conftest import auth
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    row = {"id": "ss991", "source": "ss.ge", "url": "https://home.ss.ge/ka/udzravi-qoneba/x-991", "photos": ["https://ss/1.jpg"] * 3,
           "address": "Tsatskhvebi 4", "area": 75.0, "floor": 5, "bedrooms": 2, "district": None, "price_usd": 900, "text": "x"}
    monkeypatch.setattr(M, "by_link", lambda url: row)
    monkeypatch.setattr(M, "_hashes", lambda urls: list(H[:3]))  # the owner's photos
    r = client.post(f"/api/properties/{pid}/compare-link", json={"url": "https://home.ss.ge/ka/udzravi-qoneba/x-991"}, headers=auth(vika))
    assert r.status_code == 200, r.text
    assert r.json()["listing_id"] == "ss991" and r.json()["pct"] >= 65 and "общих фото: 3" in r.json()["matched"]
    assert db.get(Listing, "ss991").status == "copy"
    monkeypatch.undo()
    r = client.post(f"/api/properties/{pid}/compare-link", json={"url": "https://example.com/1"}, headers=auth(vika))
    assert r.status_code == 400 and "myhome" in r.json()["detail"]
