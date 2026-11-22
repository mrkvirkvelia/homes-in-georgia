"""Дубли в канале (services/channel_dups.py, David 11-20): a freshly posted object that is the same flat as one already
posted → the operator is asked once; «Удалить новый пост» archives the newer one as the older's duplicate, «Не дубль»
records the pair; neither is asked again."""
from app.models import Property, SimilarDecision
from app.services import channel_dups as CD
from app.telegram import notify
from tests.conftest import make_user
from tests.test_similar import H, _object


def _posted(db, pid, msg):
    p = db.get(Property, pid)
    p.status, p.post_url = "published", f"https://t.me/rent_tbilisi_ge/{msg}"
    db.commit()


def _two(db, client):
    """Two posted objects with the same three photos (dHash): the older #old and the copy #new."""
    from app.models import PropertyMedia
    first = db.get(Property, _object(db, client, make_user(db, "agent", "Вика")))
    cols = [c.key for c in Property.__table__.columns if c.key not in ("id", "listing_id")]
    second = Property(**{c: getattr(first, c) for c in cols})
    db.add(second)
    db.flush()
    for p in (first, second):
        for n, h in enumerate(H[:3]):
            db.add(PropertyMedia(property_id=p.id, kind="photo", path=f"properties/{p.id}/{n}.jpg", position=n,
                                 dhash=h - (1 << 64) if h >= 1 << 63 else h))
    db.commit()
    _posted(db, first.id, 100)
    _posted(db, second.id, 200)
    return first.id, second.id


def test_asked_once_then_deleted(db, client, monkeypatch):
    old, new = _two(db, client)
    sent = []
    from app.services import post_sync
    monkeypatch.setattr(post_sync, "gone", lambda c, ch, m: False)
    monkeypatch.setattr(notify, "channel_duplicate", lambda k, d, pct, why: sent.append((k.id, d.id, pct)))
    assert CD.check(db, new) == 1 and sent[0][:2] == (old, new) and sent[0][2] >= 85
    assert CD.check(db, new) == 0  # asked already
    op = make_user(db, "operator", "Оля")
    assert CD.resolve(db, old, new, True, op) == "deleted"
    db.expire_all()
    d = db.get(Property, new)
    assert d is None or (d.status == "archived" and d.archive_reason == "duplicate" and d.duplicate_of == old)
    assert CD.resolve(db, old, new, True, op) == "gone"


def test_not_a_duplicate_is_remembered(db, client, monkeypatch):
    old, new = _two(db, client)
    monkeypatch.setattr(notify, "channel_duplicate", lambda *a: None)
    op = make_user(db, "operator", "Оля")
    assert CD.resolve(db, old, new, False, op) == "kept"
    assert db.query(SimilarDecision).filter_by(verdict="different").count() == 1
    assert CD.pairs_for(db, new) == [] and db.get(Property, new).status == "published"


def test_a_post_deleted_by_hand_is_not_asked(db, client, monkeypatch):
    old, new = _two(db, client)
    from app.services import post_sync
    monkeypatch.setattr(post_sync, "gone", lambda c, ch, m: m == 100)  # the old post was deleted in the channel
    monkeypatch.setattr(notify, "channel_duplicate", lambda *a: (_ for _ in ()).throw(AssertionError("asked")))
    assert CD.check(db, new) == 0


def test_posts_in_two_channels_are_not_a_duplicate(db, client):
    """11-22: #5130 (rent) / #15375 (sale) — one flat, two channels: nothing to delete."""
    old, new = _two(db, client)
    db.get(Property, new).post_url = "https://t.me/sale_in_tbilisi/73621"
    db.commit()
    assert CD.pairs_for(db, new) == []
