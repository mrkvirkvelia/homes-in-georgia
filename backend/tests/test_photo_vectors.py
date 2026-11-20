"""Stanislav 11-20: «похожие фото (другой ракурс)» — the same flat shot again or an edited copy shares no dHash photo, its
SigLIP vectors are alike (services/similar.py PHOTO_SIM_*). Fake vectors: no model in the tests."""
import json
import math
import os

import numpy as np
from sqlalchemy import text

from app import embeddings, storage
from app.models import Job, Property, PropertyMedia
from app.services import similar
from tests.conftest import auth, make_listing, make_user
from app.services.dedup import street_house
from tests.test_similar import _object

D = 768


def e(i):
    v = np.zeros(D, np.float32)
    v[i] = 1
    return v


def alike(i, c):
    """A photo with cosine c to e(i) (and ~0 to every other e(k), k < 300)."""
    return c * e(i) + math.sqrt(1 - c * c) * e(300 + i)


def lit(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def put_media(db, pid, vecs):
    for k, v in enumerate(vecs):
        m = PropertyMedia(property_id=pid, kind="photo", path=f"properties/{pid}/{k}.jpg", position=k, dhash=0)
        db.add(m)
        db.flush()
        db.execute(text("INSERT INTO photo_vectors (media_id, vec) VALUES (:m, CAST(:v AS vector))"), {"m": m.id, "v": lit(v)})
    db.commit()


def put_ad(db, lid, vecs):
    for n, v in enumerate(vecs):
        db.execute(text("INSERT INTO photo_vectors (listing_id, n, vec) VALUES (:l, :n, CAST(:v AS vector))"),
                   {"l": lid, "n": n, "v": lit(v)})
    db.commit()


def _setup(db, client, vecs, **ad):
    """Our object (2 bd, 70 m², 4th floor, Paliashvili 10) with photos e(0..2), an ad elsewhere with these photos."""
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    db.execute(text("DELETE FROM photo_vectors"))  # the origin ad's own rows: none in the tests anyway
    put_media(db, pid, [e(0), e(1), e(2)])
    kw = dict(source="myhome", urls=json.dumps(["https://myhome.ge/9001"]), address="Kazbegi 30", district="Сабуртало",
              bedrooms=None, area=None, floor=None, price_usd=2500, text="Сдаю", photos=json.dumps(["a", "b", "c", "d"]))
    make_listing(db, "mh9001", **{**kw, **ad})
    put_ad(db, "mh9001", vecs)
    return vika, pid


def _cand(db, pid, vika):
    return next((x for x in similar.find(db, f"p:{pid}", vika) if x["key"] == "l:mh9001"), None)


def test_photos_alike_without_a_shared_photo_are_shown(db, client):
    # another shoot: each of our photos has its look-alike, one of them twice (meanbest 0.96)
    vika, pid = _setup(db, client, [alike(0, 0.9), alike(2, 0.97), alike(0, 0.97), alike(1, 0.97)])
    x = _cand(db, pid, vika)
    assert x is not None and x["level"] == "maybe"
    assert x["reasons"][0].startswith(similar.PHOTO_REASON)
    # the alike ones lead the strip, the likest first
    assert x["photos"][-1] == "/api/listing-photos/mh9001/0" and set(x["photos"][:3]) == {f"/api/listing-photos/mh9001/{n}" for n in (1, 2, 3)}
    # and the other way round: the ad's card shows the object
    assert any(y["key"] == f"p:{pid}" and y["level"] == "maybe" for y in similar.find(db, "l:mh9001", vika))


def test_photos_a_little_alike_alone_are_not_shown(db, client):
    vika, pid = _setup(db, client, [alike(0, 0.86), alike(1, 0.86), alike(2, 0.86)])
    assert _cand(db, pid, vika) is None


def test_photos_a_little_alike_add_weight_to_the_same_house(db, client):
    vika, pid = _setup(db, client, [alike(0, 0.86), alike(1, 0.86), alike(2, 0.86)],
                       address="Paliashvili st 10", district="Ваке", bedrooms=2, area=74.0, floor=5)
    x = _cand(db, pid, vika)
    assert x is not None and "тот же дом" in x["reasons"] and any(r.startswith(similar.PHOTO_REASON) for r in x["reasons"])
    # the same pair without the photos: shown by the house, a lower score
    db.execute(text("DELETE FROM photo_vectors WHERE listing_id = 'mh9001'"))
    db.commit()
    y = _cand(db, pid, vika)
    assert y is not None and y["score"] < x["score"] and not any(r.startswith(similar.PHOTO_REASON) for r in y["reasons"])


def test_compare_thresholds():
    s = {"urls": set(), "cads": set(), "phones": [], "names": frozenset(), "author": None, "house": street_house(""),
         "street": frozenset(), "at": (None, None), "district": "Ваке", "floor": None, "area": None, "bedrooms": None,
         "price_usd": None}
    c = {**s, "district": None}
    assert similar.compare(s, c, 0, 0.88)[0] == "maybe"
    assert similar.compare(s, {**s, "district": "Сабуртало"}, 0, 0.88)[0] is None  # another district (Stanislav 11-20)
    assert similar.compare(s, c, 0, 0.86)[0] is None
    assert similar.compare(s, c, 0, 0.99)[0] != "same"  # never strong alone


class FakeEnc:
    """encode_images: a file's vector is e(<first byte>); an empty file is unreadable (the encoder's zero row)."""
    def __init__(self):
        self.calls = 0

    def encode_images(self, paths):
        self.calls += len(paths)
        out = []
        for p in paths:
            b = open(p, "rb").read()
            out.append(e(b[0]) if b else np.zeros(D, np.float32))
        return np.array(out)


def _rows(db, where):
    return db.execute(text(f"SELECT count(*), count(vec) FROM photo_vectors WHERE {where}")).one()


def test_backfill_is_resumable_and_idempotent(db, client, tmp_path, monkeypatch):
    vika = make_user(db, "agent", "Вика")
    pid = _object(db, client, vika)
    p = db.get(Property, pid)
    p.is_exclusive = True
    for k, b in enumerate([bytes([5]), bytes([6]), b""]):
        storage.put(f"properties/{pid}/{k}.jpg", b)
        db.add(PropertyMedia(property_id=pid, kind="photo", path=f"properties/{pid}/{k}.jpg", position=k, dhash=0))
    db.commit()
    f1, f2 = tmp_path / "1.jpg", tmp_path / "2.jpg"
    f1.write_bytes(bytes([7]))
    f2.write_bytes(bytes([8]))
    old = "2026-01-01T00:00:00+00:00"
    make_listing(db, "ss9100", photos=json.dumps([str(f1), "https://x/y.jpg", str(f2)]), first_seen=old)
    make_listing(db, "ss9101", photos=json.dumps([str(f1)]))  # new: refresh's embed.py gets the first go (NPZ_GRACE)
    monkeypatch.setenv("EMB_PATH", str(tmp_path / "none.npz"))
    enc = FakeEnc()

    # a run killed after one photo: the next one does the rest, nothing twice
    assert embeddings.embed_media(db, enc, limit=1)
    st = embeddings.run_photos(1, enc, pause=0)
    assert st["media"] >= 1 and st["ads"] == 1
    assert tuple(_rows(db, "media_id IS NOT NULL")) == (3, 2)  # the empty file: a row without a vector, not tried again
    assert tuple(_rows(db, "listing_id = 'ss9100'")) == (3, 2)  # the remote photo: no vector
    assert tuple(_rows(db, "listing_id = 'ss9101'")) == (0, 0)
    assert enc.calls == 2 + 2
    # the exclusive is searched again with its vectors
    assert db.query(Job).filter_by(kind="dup_scan", ref=str(pid), done_at=None).one().payload["trigger"] == "photo_vectors"

    assert embeddings.run_photos(1, enc, pause=0) == {"npz": 0, "media": 0, "ads": 0} and enc.calls == 4
    assert not embeddings.photos_due(db)

    # the ad's photos changed: made again from the new list
    db.execute(text("UPDATE listings SET photos = :p WHERE id = 'ss9100'"), {"p": json.dumps([str(f2)])})
    db.commit()
    embeddings.run_photos(1, enc, pause=0)
    assert tuple(_rows(db, "listing_id = 'ss9100'")) == (1, 1) and enc.calls == 5


def test_backfill_copies_the_bots_npz(db, tmp_path, monkeypatch):
    """refresh.sh embed.py already has the ad per photo: copied (no model), when its fingerprint is the ad's."""
    make_listing(db, "ss9200", photos=json.dumps(["raw/img/a.jpg", "raw/img/b.jpg"]), style="modern")
    make_listing(db, "ss9201", photos=json.dumps(["raw/img/c.jpg"]))  # embedded by the bot from other photos
    fp = embeddings._bot_embed().fingerprint
    keys = [fp({"photos": ["raw/img/a.jpg", "raw/img/b.jpg"], "style": "modern", "features": []}), fp({"photos": ["old.jpg"]})]
    np.savez(tmp_path / "v.npz", ids=np.array(["ss9200", "ss9201"]), keys=np.array(keys), img=np.zeros((2, D), np.float32),
             txt=np.zeros((2, D), np.float32), photo=np.stack([e(3), np.zeros(D, np.float32), e(4)]), owner=np.array([0, 0, 1], np.int32))
    monkeypatch.setenv("EMB_PATH", str(tmp_path / "v.npz"))
    assert embeddings.import_npz(db) == 1
    assert tuple(_rows(db, "listing_id = 'ss9200'")) == (2, 1)
    assert embeddings.import_npz(db) == 0  # done: not copied again
    assert [x.id for x in embeddings.ads_pending(db)] == ["ss9201"]
    assert os.path.exists(tmp_path / "v.npz")
