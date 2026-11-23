"""David 11-23: posts go to the channel of their kind — flats / houses for rent → the agency channel, sale / commercial /
cars → @homesingeorgia (Управление → Настройки publish_chat_<kind>); the bot not admin there → the agency channel and a
warning on the object card. Telegram is mocked (tg.call)."""
from types import SimpleNamespace

import pytest

from app.models import Property
from app.services import properties
from app.telegram import client as tg
from app.telegram import notify, store

MAIN = "-1001832464267"
REAL_NOTIFY = dict(vars(notify))  # module import time: before the autouse `sent` fixture stubs notify.*


@pytest.fixture
def bot(monkeypatch):
    """tg.call: getChatMember answers `admins` (chat -> member) else refuses; every sent message recorded."""
    for k, v in REAL_NOTIFY.items():
        if callable(v) and not k.startswith("__"):
            monkeypatch.setattr(notify, k, v)
    monkeypatch.setenv("PUBLISH_CHAT_ID", MAIN)
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setattr(notify, "storage", SimpleNamespace(fetch=lambda key, tmp: None))
    st = SimpleNamespace(admins={}, sent=[], settings={})
    monkeypatch.setattr(store, "setting", lambda k: st.settings.get(k))

    def call(method, files=None, **p):
        if method == "getChatMember":
            assert p["user_id"] == "123"
            return st.admins.get(p["chat_id"])
        st.sent.append((method, p.get("chat_id")))
        return {"message_id": 5, "chat": {"id": -100, "username": str(p.get("chat_id")).lstrip("@")}}
    monkeypatch.setattr(tg, "call", call)
    monkeypatch.setattr(tg, "send", lambda chat, text, *a, **kw: call("sendMessage", chat_id=chat))
    return st


ADMIN = {"status": "administrator", "can_post_messages": True, "can_delete_messages": True}


def _post(kind):
    return SimpleNamespace(id=None, post_channel=kind, post_text="x", post_media_keys=[], owner_id=None)


def test_kinds_route_to_their_channels(bot):
    bot.admins["@homesingeorgia"] = ADMIN
    assert notify.publish_post(_post("rent"))[2:] == (MAIN, [5], None)
    for kind in ("sale", "commercial", "cars"):
        ref = notify.publish_post(_post(kind))
        assert ref[1] == "https://t.me/homesingeorgia/5" and ref[2] == "@homesingeorgia" and ref[4] is None
    bot.settings["publish_chat_cars"] = "@cars_tbilisi"
    bot.admins["@cars_tbilisi"] = ADMIN
    assert notify.publish_post(_post("cars"))[2] == "@cars_tbilisi"


def test_bot_not_admin_falls_back_to_the_main_channel_with_a_warning(bot):
    ref = notify.publish_post(_post("sale"))  # getChatMember refused: «member list is inaccessible»
    assert ref[2] == MAIN and "@homesingeorgia" in ref[4] and bot.sent == [("sendMessage", MAIN)]
    bot.admins["@homesingeorgia"] = {"status": "administrator", "can_post_messages": True, "can_delete_messages": False}
    assert notify.publish_post(_post("sale"))[2] == MAIN  # no delete right: unpost could not take it down later


def test_channel_kind():
    p = lambda **f: Property(post_fields=f)  # noqa: E731
    assert properties.channel_kind(p()) == "rent"
    assert properties.channel_kind(p(deal="Rent", prop_type="House")) == "rent"
    assert properties.channel_kind(p(deal="Sale", prop_type="Apartment")) == "sale"
    assert properties.channel_kind(p(deal="Rent", prop_type="Commercial")) == "commercial"
    assert properties.channel_kind(p(prop_type="Warehouses")) == "commercial"


def test_publish_records_the_channel_and_the_warning(db, client, monkeypatch):
    from tests.test_publish_card import _submitted
    seen = []

    def publish_post(prop):
        seen.append(prop.post_channel)
        return 7, "https://t.me/rent_tbilisi_ge/7", MAIN, [7], "Бот не админ в @homesingeorgia"
    monkeypatch.setattr(notify, "publish_post", publish_post)
    _, nino, pid, _ = _submitted(db, client)
    p = db.get(Property, pid)
    p.post_fields = {**(p.post_fields or {}), "deal": "Sale"}
    db.commit()
    properties.publish(db, pid, nino)
    assert seen == ["sale"]
    pub = db.query(properties.PropertyPublication).filter_by(property_id=pid).one()
    assert pub.messages == {"chat": MAIN, "ids": [7], "warning": "Бот не админ в @homesingeorgia"}
    assert properties.card(db, db.get(Property, pid), nino)["publications"][0]["warning"] == "Бот не админ в @homesingeorgia"


# Irakli 11-23: «HIG Original Photos» — the photos without the watermark after a publication, once per photo set


def test_originals_post_sends_text_then_albums_of_ten(bot, monkeypatch):
    monkeypatch.setattr(store, "q", lambda sql, args: [{"path": f"k{n}"} for n in range(12)])
    monkeypatch.setattr(notify, "storage", SimpleNamespace(fetch=lambda key, tmp: f"/tmp/{key}.jpg"))
    assert notify.originals_post(5, "-4001", "🏠 x") == 12
    assert bot.sent == [("sendMessage", "-4001"), ("sendMediaGroup", "-4001"), ("sendMediaGroup", "-4001")]


def test_originals_once_per_photo_set(db, client, monkeypatch):
    from app import worker
    from app.models import PropertyMedia
    from app.services import settings
    from tests.test_publish_card import _submitted
    sent = []
    monkeypatch.setattr(notify, "publish_post", lambda prop: (7, "https://t.me/rent_tbilisi_ge/7", MAIN, [7]))
    monkeypatch.setattr(notify, "originals_post", lambda pid, chat, text: sent.append((pid, chat, text)) or 2)
    _, nino, pid, _ = _submitted(db, client)
    properties.publish(db, pid, nino)
    worker.tick()
    assert sent == []  # no chat set yet
    settings.set(db, "originals_chat_id", "-4001")
    properties.publish(db, pid, nino)
    worker.tick()
    assert len(sent) == 1 and sent[0][1] == "-4001" and f"Объект #{pid}" in sent[0][2] and "t.me/rent_tbilisi_ge/7" in sent[0][2]
    properties.publish(db, pid, nino)  # a repost, the same photos: nothing
    worker.tick()
    assert len(sent) == 1
    db.add(PropertyMedia(property_id=pid, kind="photo", path="new.jpg", position=99))
    db.commit()
    properties.publish(db, pid, nino)  # a photo added: again
    worker.tick()
    assert len(sent) == 2
