"""David 11-19 §13: the duplicate score (services/similar.py score / CONFIG) on the spec's cases 1–10, 12, 13. Fake
photo vectors: no model download."""
import json

from app import dup_eval
from app.models import Property, PropertyListing, SimilarDecision, SimilarJournal
from app.services import similar
from tests.conftest import auth, make_listing, make_user
from tests.test_photo_vectors import _cand, _setup, alike
from tests.test_similar import H, _object

F = {"address": "ул. Палиашвили 10", "district": "Ваке", "lat": 41.7085, "lng": 44.7672, "floor": 4, "area": 70.0,
     "bedrooms": 2, "price_usd": 850, "type": "apartment"}


def sc(a, b, shared=0, photo=0.0):
    return similar.score(dup_eval.profile(a), dup_eval.profile({**a, **b}), shared, photo)


def _ad_item(db, pid, lid, user):
    return next((x for x in similar.find(db, f"p:{pid}", user) if x["key"] == f"l:{lid}"), None)


def test_1_same_photos_same_street_other_owner_name(db, client):
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    make_listing(db, "mh1", source="myhome", urls=json.dumps(["https://myhome.ge/1"]), address="Paliashvili st. 10",
                 photo_hashes=json.dumps(H[:3]), text="Сдаю, хозяйка Гванца, +995 599 00 00 00")
    x = _ad_item(db, pid, "mh1", vika)
    assert x is not None and x["level"] in ("same", "maybe") and x["pct"] >= 65
    assert "общих фото: 3" in x["matched"] and x["why"].startswith(f"{x['pct']}%")
    assert x["matched_photos"] and x["photos"][: len(x["matched_photos"])] == x["matched_photos"]  # which photos matched


def test_2_cropped_watermarked_photos_found_by_vectors(db, client):
    vika, pid = _setup(db, client, [alike(0, 0.95), alike(1, 0.95), alike(2, 0.95)], address="Paliashvili 10")
    x = _cand(db, pid, vika)
    assert x is not None and x["level"] == "maybe" and x["groups"]["photo"] >= 0.7  # never «дубль» by vectors alone


def test_3_other_angles_phone_address_area_floor_is_strong(db, client):
    vika, pid = _setup(db, client, [alike(0, 0.9), alike(1, 0.9), alike(2, 0.9)], address="Paliashvili 10", bedrooms=2,
                       area=70.0, floor=4, price_usd=850, text="Сдаю, +995 555 12 34 56")
    x = _cand(db, pid, vika)
    assert x["level"] == "same" and x["pct"] >= 85 and "тот же телефон собственника" in x["matched"]


def test_4_no_phone_photos_address_area(db, client):
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    make_listing(db, "mh4", source="myhome", urls=json.dumps(["https://myhome.ge/4"]), text="Сдаю квартиру",
                 address="Paliashvili 10", area=70.5, photo_hashes=json.dumps(H[:2]))
    assert _ad_item(db, pid, "mh4", vika)["level"] == "same"


def test_5_one_phone_on_several_flats_is_not_merged():
    owner = {"phones": ["+995 577 11 22 33"], "multi": ["577112233"]}
    other_flat = {"address": "Kazbegi 30", "district": "Сабуртало", "lat": 41.727, "lng": 44.755, "floor": 9, "area": 110.0,
                  "bedrooms": 3, "price_usd": 1400}
    assert sc({**F, **owner}, other_flat)["level"] is None
    # the same house, other floor and area: shown at most, never «дубль»
    assert sc({**F, **owner}, {"floor": 8, "area": 90.0})["level"] != "same"


def test_6_same_house_floor_area_other_photos_and_flat_numbers():
    r = sc({**F, "address": "ул. Палиашвили 10, кв. 12"}, {"address": "Paliashvili 10, apt 15"})
    assert r["level"] != "same" and "flat" in r["penalty"] and "квартиры №12 / №15" in r["differs"]
    # and the same house, floor and area alone (no numbers, no photos, no contact): not «дубль» either
    assert sc(F, {"address": "Paliashvili 10"})["level"] != "same"


def test_7_developer_stock_photos_do_not_confirm():
    r = sc({**F, "address": "Kazbegi 25", "floor": 3, "area": 65.0}, {"floor": 9, "area": 80.0, "price_usd": 950}, shared=3)
    assert r["level"] != "same"


def test_8_address_in_three_scripts_is_one_building():
    keys = {similar.building_key(a) for a in ("ул. Палиашвили, 10", "10 Paliashvili St", "ფალიაშვილის ქუჩა 10", "Paliashvili str. 10")}
    assert len(keys) == 1 and None not in keys
    assert similar.building_key("Paliashvili 12") not in keys
    r = sc({**F, "phones": ["555123456"]}, {"address": "ფალიაშვილის ქუჩა 10"})
    assert r["groups"]["location"] == 1.0 and r["level"] == "same"


def test_9_area_45_45_0_45_05_compatible():
    for b in (45, 45.0, 45.05):
        r = sc({**F, "area": 45.0}, {"area": b})
        assert r["groups"]["property"] == 1.0 and not r["differs"]


def test_10_price_changed_still_found():
    r = sc(F, {"price_usd": 650}, shared=3)
    assert r["level"] == "same" and "цена другая" in r["differs"]


def test_12_different_cadastres_never_auto(db, client):
    r = sc({**F, "cads": ["01.10.12.003.045.01.503"], "phones": ["555123456"]}, {"cads": ["01.10.12.003.045.01.507"]}, shared=3)
    assert r["level"] != "same" and "cadastre" in r["penalty"]
    # a parcel's code inside a flat's: no contradiction
    assert "cadastre" not in sc({**F, "cads": ["01.10.12.003.045"]}, {"cads": ["01.10.12.003.045.01.503"]})["penalty"]


def test_13_reprocessing_a_pair_is_idempotent(db, client, monkeypatch):
    from app.services import matching
    from app.services import properties as P
    sent, notes = [], []
    monkeypatch.setattr(matching, "_send", lambda alerts: sent.append(alerts))
    monkeypatch.setattr(P, "_notify", lambda kind, *a: notes.append(kind))
    vika, op = make_user(db, "agent", "Вика"), make_user(db, "operator", "Оля")
    pid = _object(db, client, vika)
    db.get(Property, pid).is_exclusive = True
    db.commit()
    make_listing(db, "mh13", source="myhome", urls=json.dumps(["https://myhome.ge/13"]), photo_hashes=json.dumps(H[:3]))
    # the scan of the exclusive, twice: one message
    similar.scan_exclusive(db, pid)
    similar.scan_exclusive(db, pid)
    assert notes.count("exclusive_duplicates") == 1
    # «Дубль» twice: one link, one journal row, the second call sends nothing
    body = {"a": f"p:{pid}", "b": "l:mh13", "same": True}
    assert client.post("/api/similar/decide", json=body, headers=auth(op)).json()["linked_to"] == pid
    r = client.post("/api/similar/decide", json=body, headers=auth(op)).json()
    assert r["repeat"] is True and r["linked_to"] is None
    assert db.query(PropertyListing).filter_by(listing_id="mh13").count() == 1 and len(sent) <= 1
    j = db.query(SimilarJournal).one()
    assert (j.verdict, j.decided_by, j.a, j.b) == ("same", op.id, "l:mh13", f"p:{pid}")
    assert j.score >= 0.85 and j.level == "same" and "общих фото: 3" in j.features["matched"]


def test_review_verdict_keeps_the_pair_listed_and_journals(db, client):
    vika, ana = make_user(db, "agent", "Вика"), make_user(db, "agent", "Аня")
    pid = _object(db, client, vika)
    make_listing(db, "mh14", source="myhome", urls=json.dumps(["https://myhome.ge/14"]), photo_hashes=json.dumps(H[:1]),
                 address="other 1", district="Сабуртало")
    r = client.post("/api/similar/decide", json={"a": "l:mh14", "b": f"p:{pid}", "verdict": "review"}, headers=auth(ana))
    assert r.json()["verdict"] == "review"
    x = _ad_item(db, pid, "mh14", vika)
    assert x is not None and x["decided"] == "review"
    assert db.query(SimilarDecision).one().verdict == "review"
    client.post("/api/similar/decide", json={"a": "l:mh14", "b": f"p:{pid}", "same": False}, headers=auth(ana))
    assert [j.verdict for j in db.query(SimilarJournal).order_by(SimilarJournal.id)] == ["review", "different"]
    assert db.query(SimilarJournal).order_by(SimilarJournal.id.desc()).first().prev == "review"
    assert _ad_item(db, pid, "mh14", vika) is None


def test_labelled_pairs_precision_first():
    m = dup_eval.synthetic(out=lambda *_: None)
    assert m["auto_false"] == 0 and m["auto_precision"] == 1.0  # an automatic «дубль» is never another flat
    assert m["shown_recall"] == 1.0  # every labelled duplicate reaches the operator
