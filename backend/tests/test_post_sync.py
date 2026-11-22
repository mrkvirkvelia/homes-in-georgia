"""Сверка с каналом (services/post_sync.py): an object whose channel post is gone leaves the site; a live post, an odd
answer and a mass «gone» (t.me down) change nothing. No network: a fake httpx transport."""
import httpx

from app.models import Event, Property
from app.services import post_sync
from tests.conftest import make_user
from tests.test_similar import _object

LIVE = '<div class="tgme_widget_message"><div class="tgme_widget_message_text">x</div></div>'
GONE = '<div class="tgme_widget_message_error">Post not found</div>'


def _fake(monkeypatch, pages):
    def handler(req):
        msg = int(req.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, text=pages.get(msg, "")) if msg in pages else httpx.Response(502)
    real = httpx.Client
    monkeypatch.setattr(post_sync.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def _pubs(db, client, msgs):
    """Published objects, one per channel post id: copies of tests.test_similar._object's object."""
    first = db.get(Property, _object(db, client, make_user(db, "agent", "Вика")))
    cols = [c.key for c in Property.__table__.columns if c.key not in ("id", "listing_id")]
    out = []
    for n, msg in enumerate(msgs):
        p = first if n == 0 else Property(**{c: getattr(first, c) for c in cols})
        db.add(p)
        p.status, p.site_hidden, p.post_url = "published", False, f"https://t.me/rent_tbilisi_ge/{msg}"
        db.flush()
        out.append(p.id)
    db.commit()
    return out


def test_a_deleted_post_takes_the_object_off_the_site(db, client, monkeypatch):
    live, dead, odd = _pubs(db, client, (101, 102, 103))
    _fake(monkeypatch, {101: LIVE, 102: GONE})  # 103: a 502
    assert post_sync.run(db, pause=0) == 1
    db.expire_all()
    assert [db.get(Property, x).site_hidden for x in (live, dead, odd)] == [False, True, False]
    ev = db.query(Event).filter_by(entity="property", entity_id=str(dead), action="site_off").one()
    assert ev.actor_label == "сверка с каналом" and ev.data["reason"] == "пост удалён в канале"


def test_mass_gone_hides_nothing(db, client, monkeypatch):
    pids = _pubs(db, client, [200 + n for n in range(12)])
    _fake(monkeypatch, {200 + n: GONE for n in range(12)})
    assert post_sync.run(db, pause=0) == 0
    db.expire_all()
    assert not any(db.get(Property, x).site_hidden for x in pids)
