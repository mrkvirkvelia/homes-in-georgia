"""Stage 4: new ads are matched to objects (same → linked, similar → operator review), exclusive conflicts block
publishing until the outside ad is checked as removed."""
import pytest
from sqlalchemy import func, select, text

from app.models import Event, ListingMatch, Owner, Property, PropertyListing, PropertyMedia
from app.services import matching
from app.services import properties as P
from app.services.common import jdump
from app.services.errors import DomainError
from tests.conftest import auth, make_listing, make_user

PHOTOS = jdump([0x0F0F0F0F0F0F0F0F, 0x123456789ABCDEF0, 0x00FF00FF00FF00FF])


def _object(db, agent, lid="ss8000", phone="+995 555 12 34 56", **kw):
    """An object taken from listing `lid` with a known owner."""
    make_listing(db, lid, photo_hashes=kw.pop("photo_hashes", "[]"))
    p = P.take(db, lid, agent)
    o = Owner(name="Нана", phone=phone, phone_norm=phone.replace(" ", "").replace("+995", ""))
    db.add(o)
    db.flush()
    p.owner_id = o.id
    for k, v in kw.items():
        setattr(p, k, v)
    db.commit()
    return p


def _verdict(db, p, **listing):
    l = make_listing(db, listing.pop("id", "mh9000"), source="myhome", urls='["https://myhome.ge/9000"]', **listing)
    return matching.verdict(matching._feat(l), matching._objects(db, [p.id])[p.id])


def test_verdicts(db):
    p = _object(db, make_user(db), cadastral_code="01.14.05.003.017", photo_hashes=PHOTOS)
    # same owner phone + same address (the default listing text has the owner's phone)
    v, _, why = _verdict(db, p, id="mh9001", address="Палиашвили 10", text="call +995 555123456")
    assert v == "same" and "тот же телефон и адрес" in why
    # cadastral code in the text
    assert _verdict(db, p, id="mh9002", address=None, text="кадастр 01.14.05.003.017")[0] == "same"
    # two shared photos (dHash 1 bit off), different text and phone
    hashes = jdump([0x0F0F0F0F0F0F0F0E, 0x123456789ABCDEF0])
    v, _, why = _verdict(db, p, id="mh9003", address="другой", text="звоните 599 00 00 00", photo_hashes=hashes)
    assert v == "same" and why == ["общих фото: 2"]
    # the params alone (district, bedrooms, floor, area) name no flat (eval 11-17: 0 of 5): the address hint shows it
    assert _verdict(db, p, id="mh9004", address="Палиашвили 10", text="599 00 00 00", area=70.5)[0] == "none"
    # another area (60 vs 70 m², 11-13: 52 vs 60) → nothing; within 10% a person compares (11-17: 100 vs 110)
    assert _verdict(db, p, id="mh9005", address="Палиашвили 10", text="599 00 00 00", area=60.0)[0] == "none"
    # one shared photo is not enough to link (a common building shot), but a person compares, whatever the floor
    one = jdump([0x0F0F0F0F0F0F0F0F])
    assert _verdict(db, p, id="mh9006", address="x", text="-", floor=5, photo_hashes=one)[:3:2] == ("similar", ["одно общее фото"])
    assert _verdict(db, p, id="mh9016", address="x", text="-", floor=9, photo_hashes=one)[0] == "none"  # 5 floors off
    # the owner's phone alone (another address): his other flat or this one, a «похож» card, not a link
    assert _verdict(db, p, id="mh9007", address="x")[:3:2] == ("similar", ["тот же телефон", "район, спальни, этаж и площадь совпадают"])
    # the phone and one shared photo: the same flat
    assert _verdict(db, p, id="mh9008", address="x", floor=9, photo_hashes=one)[:3:2] == ("same", ["тот же телефон и общее фото"])
    # an agent's number in our base names no flat
    db.execute(text("UPDATE owners SET is_agent = true"))
    db.commit()
    assert _verdict(db, p, id="mh9009", address="x", floor=9)[0] == "none"


def test_object_photos_beat_floor_and_area(db, client):
    """David 11-17: our channel object #15032 (1 Shroshi St, 110 m², 5th floor) and the ss.ge ad «Vake shrosha st. 1»
    (100 m², 6th floor) show the same rooms. The object's own photos (property_media.dhash) link the ad."""
    nino = make_user(db, "operator", "Нино")
    p = Property(address="1 Shroshi St", district="Ваке", bedrooms=2, area=110, floor=5, price=1000, status="published")
    db.add(p)
    db.flush()
    signed = [h - (1 << 64) if h >> 63 else h for h in (0xF0F0F0F0F0F0F0F0, 0x0123456789ABCDEF, 0xFFFF0000FFFF0000)]
    db.add_all(PropertyMedia(property_id=p.id, path=f"properties/{p.id}/{n}.jpg", kind="photo", dhash=h)
               for n, h in enumerate(signed))
    db.commit()
    # the site's watermark flips a couple of bits
    make_listing(db, "ss35073525", address="Vake shrosha st. 1", area=100, floor=6, price_usd=1000, text="-",
                 photo_hashes=jdump([0xF0F0F0F0F0F0F0F1, 0xFFFF0000FFFF0003, 0x1111111111111111]))
    make_listing(db, "ss35073526", address="Vake shrosha st. 1", area=100, floor=6, text="-",
                 photo_hashes=jdump([0x0123456789ABCDEF]))  # one shared photo: a person compares
    assert matching.process(db, ["ss35073525", "ss35073526"]) == {"same": 1, "similar": 1, "none": 0}
    assert db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == "ss35073525")) == p.id
    item = next(i for i in client.get("/api/listings/new", headers=auth(nino)).json()["items"] if i["id"] == "ss35073526")
    assert item["matches"][0]["property_id"] == p.id and item["matches"][0]["reasons"] == ["одно общее фото"]
    assert item["url"] == "https://ss.ge/ss35073526"  # the source link before «Беру в работу»


def test_photo_hash_is_the_ingest_dhash(tmp_path):
    from PIL import Image
    f = tmp_path / "a.jpg"
    Image.effect_mandelbrot((64, 48), (-2, -1.5, 1, 1.5), 50).convert("RGB").save(f)
    h = matching.photo_hash(f.read_bytes())
    assert h & matching.U64 == matching._ingest().dhash(str(f)) and -(1 << 63) <= h < (1 << 63)
    assert matching.photo_hash(b"not an image") is None


def test_media_backfill_and_rematch(db, monkeypatch):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.effect_mandelbrot((64, 48), (-2, -1.5, 1, 1.5), 50).convert("RGB").save(buf, "JPEG")
    from app import storage
    monkeypatch.setattr(storage, "read", lambda key: None if key.startswith("previews/") else buf.getvalue())
    p = Property(address="x", status="archived")
    db.add(p)
    db.flush()
    db.add(PropertyMedia(property_id=p.id, path="legacy/1.jpg", kind="photo"))
    db.commit()
    assert matching.backfill_media_hashes(db, out=lambda *_: None) == 1
    h = db.scalar(select(PropertyMedia.dhash)) & matching.U64
    make_listing(db, "ss7001", address="y", text="-", photo_hashes=jdump([h, h ^ 1]))
    db.add(ListingMatch(listing_id="ss7001", property_id=p.id, status="pending", reasons=["старое"]))
    db.commit()
    assert matching.rematch(db) == {"same": 1, "similar": 0, "none": 0}
    assert db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == "ss7001")) == p.id


def test_embedding_similarity_when_vectors_exist(db, monkeypatch):
    p = _object(db, make_user(db))
    vec = [1.0] + [0.0] * 767
    db.execute(text("UPDATE properties SET text_embedding = CAST(:v AS vector) WHERE id = :i"),
               {"v": "[" + ",".join(map(str, vec)) + "]", "i": p.id})
    db.commit()

    class Enc:
        @staticmethod
        def encode_texts(ts):
            return [vec]
    from app import embeddings
    monkeypatch.setattr(embeddings, "encoder", lambda: Enc)
    l = make_listing(db, "mh9100", source="myhome", urls="[]", address="x", text="-", floor=None, description_ru="Уютная")
    found = matching.match(db, l)
    assert found[0]["verdict"] == "similar" and found[0]["reasons"][0].startswith("похожее описание")
    # a similar text alone, another floor → no card (11-13)
    l2 = make_listing(db, "mh9101", source="myhome", urls="[]", address="x", text="-", floor=9, description_ru="Уютная")
    assert matching.match(db, l2) == []


def test_new_listings_are_linked_or_queued_and_feed_shows_them(db, client, sent):
    georgiy = make_user(db, "agent", "Георгий")
    nino = make_user(db, "operator", "Нино")
    p = _object(db, georgiy)
    make_listing(db, "mh9201", source="myhome", urls='["https://myhome.ge/9201"]', address="Палиашвили 10")  # same phone
    make_listing(db, "mh9202", source="myhome", urls='["https://myhome.ge/9202"]', address="—")  # the owner's phone
    make_listing(db, "mh9203", source="myhome", urls="[]", district="Сабуртало", text="-")
    assert matching.process(db, ["mh9201", "mh9202", "mh9203"]) == {"same": 1, "similar": 1, "none": 1}
    assert db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == "mh9201")) == p.id
    assert db.scalar(select(Event.action).where(Event.action == "listing_linked")) == "listing_linked"
    m = db.scalar(select(ListingMatch).where(ListingMatch.listing_id == "mh9202"))
    assert (m.property_id, m.status) == (p.id, "pending")
    assert sent.of("exclusive_conflict") == []  # not an exclusive

    feed = client.get("/api/listings/new", headers=auth(nino)).json()
    by = {i["id"]: i for i in feed["items"]}
    assert "mh9201" not in by and feed["known_total"] == 1  # known ads don't clutter the feed
    assert by["mh9202"]["matches"][0]["property_id"] == p.id and by["mh9203"]["matches"] == []
    known = {i["id"]: i for i in client.get("/api/listings/new?known=1", headers=auth(nino)).json()["items"]}
    assert known["mh9201"]["known_object"]["id"] == p.id

    # an agent can't decide; the operator says «Тот же объект»
    assert client.post(f"/api/listings/mh9202/matches/{p.id}", json={"same": True}, headers=auth(georgiy)).status_code == 403
    assert client.post(f"/api/listings/mh9202/matches/{p.id}", json={"same": True}, headers=auth(nino)).json()["status"] == "confirmed"
    assert db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == "mh9202")) == p.id
    # taking a known ad opens its object instead of creating a twin
    assert P.take(db, "mh9202", georgiy).id == p.id
    assert db.scalar(select(func.count()).select_from(Property)) == 1


def test_sync_runs_the_matcher(db):
    p = _object(db, make_user(db))
    import json
    import sys
    from app.config import REPO_ROOT
    sys.path.append(str(REPO_ROOT / "bot"))
    import db as botdb
    item = {"id": "mh9301", "source": "myhome.ge", "owner_id": "x", "urls": ["https://myhome.ge/9301"], "price_usd": 850,
            "area": 70.0, "floor": 4, "bedrooms": 2, "address": "Палиашвили 10", "district": "Ваке", "latlng": None,
            "photos": [], "photo_hashes": [1, 2], "text": "собственник 555 12 34 56", "agent_reasons": []}
    botdb.URL = None  # DATABASE_URL = the backend test DB (conftest)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "listings.json"
        f.write_text(json.dumps([item]))
        botdb.sync(str(f), str(Path(tmp) / "none.json"), full=False)
    db.expire_all()
    assert db.scalar(select(PropertyListing.property_id).where(PropertyListing.listing_id == "mh9301")) == p.id
    assert db.scalar(text("SELECT photo_hashes FROM listings WHERE id = 'mh9301'")) == "[1, 2]"


def test_exclusive_conflict_flags_notifies_and_blocks_publishing(db, client, sent):
    georgiy = make_user(db, "agent", "Георгий")
    nino = make_user(db, "operator", "Нино")
    p = _object(db, georgiy, lid="tg8100", is_exclusive=True)  # taken from our own channel post: no conflict yet
    db.execute(text("UPDATE listings SET source = 'agency' WHERE id = 'tg8100'"))
    db.execute(text("UPDATE properties SET status = 'review' WHERE id = :i"), {"i": p.id})
    db.add(PropertyMedia(property_id=p.id, path="x/8100.jpg", kind="photo"))  # publishing needs a photo
    db.commit()
    assert client.get(f"/api/properties/{p.id}", headers=auth(nino)).json()["exclusive_conflict"] == []

    make_listing(db, "ss8101", urls='["https://ss.ge/8101"]', address="Палиашвили 10")  # the owner posted it on ss.ge
    matching.process(db, ["ss8101"])
    assert [a[1:] for a in sent.of("exclusive_conflict")] == [("ss.ge", "https://ss.ge/8101")]
    assert db.scalar(select(Event.data).where(Event.action == "exclusive_conflict"))["listing_id"] == "ss8101"
    card = client.get(f"/api/properties/{p.id}", headers=auth(nino)).json()
    assert [(a["source"], a["url"]) for a in card["exclusive_conflict"]] == [("ss", "https://ss.ge/8101")]
    row = client.get("/api/properties?status=review", headers=auth(nino)).json()["items"][0]  # lists show it too
    assert row["exclusive_conflict"][0]["source"] == "ss"
    other = make_user(db, "agent", "Леван")  # another agent can't open someone else's object under review at all
    assert client.get(f"/api/properties/{p.id}", headers=auth(other)).status_code == 404

    r = client.post(f"/api/properties/{p.id}/publish", headers=auth(nino))
    assert r.status_code == 409 and r.json()["code"] == "exclusive_conflict"
    r = client.post(f"/api/properties/{p.id}/review", json={"approve": True}, headers=auth(nino))
    assert r.status_code == 409
    with pytest.raises(DomainError):
        P.publish(db, p.id, nino)
    db.rollback()

    # «Проверено: снято» (operator only) clears it; then it publishes as an exclusive
    assert client.post(f"/api/properties/{p.id}/listings/ss8101/removed", headers=auth(georgiy)).status_code == 403
    r = client.post(f"/api/properties/{p.id}/listings/ss8101/removed", headers=auth(nino)).json()
    assert r["exclusive_conflict"] == [] and r["listings"][-1]["removed_checked_at"]
    assert client.post(f"/api/properties/{p.id}/publish", headers=auth(nino)).json()["status"] == "published"


def test_marking_exclusive_shows_where_else_it_is(db, client):
    georgiy = make_user(db, "agent", "Георгий")
    p = _object(db, georgiy)
    make_listing(db, "mh9401", source="myhome", urls='["https://myhome.ge/9401"]', address="Палиашвили 10")  # not linked
    got = client.get(f"/api/properties/{p.id}/elsewhere", headers=auth(georgiy)).json()["items"]
    assert {(x["listing_id"], x["verdict"]) for x in got} == {("ss8000", "linked"), ("mh9401", "same")}
    r = client.patch(f"/api/properties/{p.id}", json={"is_exclusive": True}, headers=auth(georgiy)).json()
    assert [a["listing_id"] for a in r["exclusive_conflict"]] == ["ss8000"]  # its own origin ad on ss.ge is still live
