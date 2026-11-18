"""Preparing an object (Stanislav 2026-11-11): cadastral code format, 9 photos + 1 video, rooms optional."""
import pytest

from app.models import Property
from app.services import properties, settings
from app.services.common import clean_cadastral
from app.services.errors import DomainError
from tests.conftest import auth, make_listing, make_user


@pytest.mark.parametrize("raw,clean", [
    ("01.14.12.003.045", "01.14.12.003.045"),
    ("01.10.10.02.20.0.01.01.84A", "01.10.10.02.20.0.01.01.84A"),
    ("01.10.13.015.029.01.150ა", "01.10.13.015.029.01.150ა"),
    (" 01,14 12..003.045. ", "01.14.12.003.045"),
    ("N01.14.02.025.242.01.01.285", "01.14.02.025.242.01.01.285"),
    ("01.14.11.020.001.01.088 а", "01.14.11.020.001.01.088а"),
    ("01.13.06.008", "01.13.06.008"),
    ("01.14.12.003.045/2", "01.14.12.003.045/2"),
    ("", None), (None, None),
])
def test_cadastral_ok(raw, clean):
    assert clean_cadastral(raw) == clean


@pytest.mark.parametrize("raw", ["Test", "?", "1", "01.", "2010-10-01", "17 Tashkenti Street", "01.14.12",
                                 "01.10.14.005.009.01.011\t03.09.2025", "01.14.11.037.012.01.01.035 | 01.14.11.037"])
def test_cadastral_garbage(raw):
    with pytest.raises(DomainError) as e:
        clean_cadastral(raw)
    assert e.value.code == "bad_cadastral" and e.value.status == 422 and "01.14.12.003.045" in e.value.message


def _object(db, lid="ss901"):
    ag = make_user(db, "agent")
    p = properties.take(db, make_listing(db, lid).id, ag)
    properties.call_result(db, p.id, ag, True)
    properties.owner_or_agent(db, p.id, ag, True, "Нана", "599 11 22 33")
    return ag, p


def test_cadastral_checked_only_when_changed(db, client):
    ag, p = _object(db)
    p.cadastral_code = "старый код из таблицы"  # a legacy value: saving other fields keeps working
    db.commit()
    r = client.patch(f"/api/properties/{p.id}", headers=auth(ag), json={"cadastral_code": "старый код из таблицы", "area": 50})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/properties/{p.id}", headers=auth(ag), json={"cadastral_code": "мусор"})
    assert r.status_code == 422 and r.json()["code"] == "bad_cadastral"
    r = client.patch(f"/api/properties/{p.id}", headers=auth(ag), json={"cadastral_code": "01 14 12 003 045"})
    assert r.status_code == 200 and r.json()["cadastral_code"] == "01.14.12.003.045"


def test_deal_form_cadastral(db, client):
    ag = make_user(db, "agent")
    body = {"agent_id": ag.id, "price": 800, "rent_from": "2030-01-01", "address": "Пекини 1"}
    r = client.post("/api/deals", headers=auth(ag), json={**body, "cadastral": "нет"})
    assert r.status_code == 422 and r.json()["code"] == "bad_cadastral"
    r = client.post("/api/deals", headers=auth(ag), json={**body, "cadastral": "01,14,12,003,045"})
    assert r.status_code == 200 and r.json()["cadastral"] == "01.14.12.003.045"


def test_media_limit_40_photos_1_video(db):
    ag, p = _object(db, "ss902")
    properties.upload_media(db, p.id, [(f"{i}.jpg", b"\xff\xd8x") for i in range(40)], None, ag)
    properties.upload_media(db, p.id, [("v.mp4", b"\0\0video")], None, ag)
    for extra in ("41.jpg", "v2.mov"):
        with pytest.raises(DomainError) as e:
            properties.upload_media(db, p.id, [(extra, b"\xff\xd8x")], None, ag)
        assert e.value.code == "media_limit" and e.value.status == 422
    # a batch that overflows adds nothing
    m = properties.media(db, p.id)
    properties.delete_media(db, p.id, m[0].id, ag)
    with pytest.raises(DomainError):
        properties.upload_media(db, p.id, [("a.jpg", b"\xff\xd8x"), ("b.jpg", b"\xff\xd8x")], None, ag)
    assert len(properties.media(db, p.id)) == 40


def test_upload_lost_the_last_slot_to_a_parallel_one_leaves_no_files(db, monkeypatch):
    """Files go to the storage before the row lock (3 parallel uploads don't queue, Irakli 11-18); the limit is checked
    again under the lock, and the loser's files are deleted."""
    from pathlib import Path
    from app.config import settings as env
    ag, p = _object(db, "ss903")
    properties.upload_media(db, p.id, [("v.mp4", b"\0\0video")], None, ag)
    m = properties.media(db, p.id)
    properties.delete_media(db, p.id, m[0].id, ag)
    real, calls = properties._media_check, []

    def race(db_, p_, actor, kinds):
        calls.append(1)
        if len(calls) == 2:  # under the lock: a parallel upload has taken the video slot meanwhile
            properties.upload_media(db_, p_.id, [("other.mp4", b"\0\0v2")], None, actor)
        return real(db_, p_, actor, kinds)
    monkeypatch.setattr(properties, "_media_check", race)
    with pytest.raises(DomainError) as e:
        properties.upload_media(db, p.id, [("v.mp4", b"\0\0video")], None, ag)
    assert e.value.code == "media_limit"
    left = [f.name for f in Path(env.MEDIA_DIR, "properties", str(p.id)).iterdir()]
    assert len(left) == 1 and [x.path for x in properties.media(db, p.id)] == [f"properties/{p.id}/{left[0]}"]


def test_min_9_photos_to_review_and_publish(db, monkeypatch):
    monkeypatch.setattr(properties, "MIN_PHOTOS", 9)
    ag, p = _object(db, "ss904")
    properties.upload_media(db, p.id, [(f"{i}.jpg", b"\xff\xd8x") for i in range(8)] + [("v.mp4", b"\0\0video")], None, ag)
    with pytest.raises(DomainError) as e:
        properties.require_min_photos(db, p)
    assert e.value.code == "few_photos" and "минимум 9 фото, сейчас 8" in e.value.message
    properties.upload_media(db, p.id, [("9.jpg", b"\xff\xd8x")], None, ag)
    properties.require_min_photos(db, p)  # 9 photos: ok


def test_album_first_9_photos_and_the_video():
    from app.telegram.notify import _album as album
    items = [("photo", n) for n in range(15)] + [("video", "v")]
    assert album(items) == [("photo", n) for n in range(9)] + [("video", "v")]
    assert album([("video", "v")] + items[:12]) == [("video", "v")] + items[:9]
    assert album(items[:3]) == items[:3]


def test_rooms_optional_and_switchable(db):
    ag, p = _object(db, "ss903")
    properties.upload_media(db, p.id, [("a.jpg", b"\xff\xd8x")], None, ag)  # no room
    p = db.get(Property, p.id)
    assert not any("комнат" in x for x in properties.missing_fields(p))
    assert properties.out(db, p, ag, full=True)["room_picker"] is True
    settings.set(db, "room_picker", "0")
    assert properties.out(db, p, ag, full=True)["room_picker"] is False


def test_media_order_saved_and_rooms_photo_only(db, client):
    ag, p = _object(db, "ss904")
    properties.upload_media(db, p.id, [("a.jpg", b"\xff\xd8x"), ("b.jpg", b"\xff\xd8x")], "Кухня", ag)
    properties.upload_media(db, p.id, [("v.mp4", b"\0v")], "Кухня", ag)
    a, b, v = properties.media(db, p.id)
    assert (a.room, v.room) == ("Кухня", None)  # a video never gets a room
    assert properties.set_media_room(db, p.id, v.id, "Спальня 1", ag).room is None
    r = client.put(f"/api/properties/{p.id}/media/order", headers=auth(ag), json={"ids": [v.id, b.id, a.id]})
    assert r.status_code == 200, r.text
    assert [m["id"] for m in r.json()["media"]] == [v.id, b.id, a.id]
    db.expire_all()
    assert [m.id for m in properties.media(db, p.id)] == [v.id, b.id, a.id]  # the album (notify.media_paths) reads position
    r = client.put(f"/api/properties/{p.id}/media/order", headers=auth(ag), json={"ids": [a.id, b.id]})
    assert r.status_code == 409 and r.json()["code"] == "bad_order"
    other = make_user(db, "agent")
    assert client.put(f"/api/properties/{p.id}/media/order", headers=auth(other), json={"ids": [a.id, b.id, v.id]}).status_code == 403
    r = client.post(f"/api/properties/{p.id}/media", headers=auth(ag), files={"files": ("c.jpg", b"\xff\xd8x", "image/jpeg")})
    assert r.status_code == 200, r.text
    assert r.json()["uploaded_ids"] == [r.json()["media"][-1]["id"]]  # the UI maps parallel uploads to the selection order
