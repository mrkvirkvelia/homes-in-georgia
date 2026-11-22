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
