"""Посты канала → объекты (services/channel_import.py), удалённый пост → архив (services/post_sync.py). No Telegram:
channel_import.ask is faked, no map lookups."""
import base64
import io

from PIL import Image

from app.models import Event, Property, PropertyMedia
from app.services import channel_import as CI
from app.services import post_sync
from tests.conftest import make_user

TEXT = """#Vera 🚇 #Rustaveli
📍16-18-20 Simon Janashia St

🏢 #2Bed #Apartment for #Rent
✨ #NewBuilding | #Mixed
🏠 115 sq.m | 6/8 Floor | #CentralHeating | #Bath
👬Tenants: 1-4
🐕Pets: #ByAgreement
💰 1300$ + Deposit 1300$
📲 @David_Tibelashvili | +995 599 20 67 16 #Roman2"""


def _jpg(c):
    b = io.BytesIO()
    Image.new("RGB", (64, 48), c).save(b, "JPEG")
    return base64.b64encode(b.getvalue()).decode()


def _post(msg, text=TEXT):
    return {"id": msg, "date": "2026-11-22T08:00:00+00:00", "text": text, "links": [],
            "photos": [{"id": msg * 10 + n, "b64": _jpg((n * 60, 90, 120))} for n in range(3)]}


def _fake(monkeypatch, channel_posts, there=None):
    def ask(path, body, timeout=250):
        if path == "/channel":
            return {"ok": True, "posts": [p for p in channel_posts if p["id"] > body["min_id"]
                                          and (not body["max_id"] or p["id"] < body["max_id"])]}
        return None if there is None else {"ok": True, "ids": [i for i in body["ids"] if i in there]}
    monkeypatch.setattr(CI, "ask", ask)
    monkeypatch.setattr(CI, "_point", lambda p: None)


def test_a_channel_post_becomes_a_published_object_once(db, monkeypatch):
    roman = make_user(db, "agent", "Роман")
    roman.agent_tag = "Roman2"
    db.commit()
    _fake(monkeypatch, [_post(500), _post(501, "❗️#FlatRented\nNice apartment in 📍Vera found a tenant")])
    assert CI.run(db) == {"created": 1, "not_object": 1}
    p = db.query(Property).one()
    assert (p.status, p.site_hidden, p.post_url) == ("published", False, "https://t.me/rent_tbilisi_ge/500")
    assert (p.address, p.bedrooms, float(p.area), p.floor, p.total_floors, float(p.price)) == \
        ("16-18-20 Simon Janashia St", 2, 115.0, 6, 8, 1300.0)
    assert p.agent_id == roman.id and p.post_fields["pets"] == "ByAgreement" and p.post_fields["deposit"] == 1300
    assert db.query(PropertyMedia).filter_by(property_id=p.id, kind="photo").count() == 3
    assert CI.run(db) == {}  # the cursor moved past 501: nothing new


def test_a_repost_moves_the_link_and_a_deleted_post_archives(db, monkeypatch):
    _fake(monkeypatch, [_post(600)])
    CI.run(db)
    pid = db.query(Property).one().id
    _fake(monkeypatch, [_post(600), _post(610)])  # the same flat posted again
    assert CI.run(db) == {"relinked": 1}
    assert db.query(Property).count() == 1 and db.get(Property, pid).post_url.endswith("/610")

    _fake(monkeypatch, [], there=set())  # the account says 610 is gone
    assert post_sync.run(db, pause=0) == 1
    db.expire_all()
    p = db.get(Property, pid)
    assert (p.status, p.archive_reason) == ("archived", "not_actual")
    assert db.query(Event).filter_by(entity_id=str(pid), action="archived").one().actor_label == "сверка с каналом"

    _fake(monkeypatch, [_post(620)])  # posted once more: back from the archive
    assert CI.run(db) == {"relinked": 1}
    db.expire_all()
    assert db.get(Property, pid).status == "published"
