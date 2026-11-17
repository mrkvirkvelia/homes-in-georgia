"""Audit: file URLs carry a short-lived purpose="media" token, not the session JWT. It opens GET /api/media/… only,
only from the query string; the session token in the query is refused (a copied photo link is not a CRM login)."""
import jwt

from app import storage
from app.api.deps import ALG, create_token
from app.config import settings
from app.services import properties
from tests.conftest import auth, make_listing, make_user


def _photo(db):
    ag = make_user(db, "agent")
    p = properties.take(db, make_listing(db, "ss88").id, ag)
    properties.call_result(db, p.id, ag, True)
    properties.owner_or_agent(db, p.id, ag, True, "Нана", "599 11 22 33")
    (m,) = properties.upload_media(db, p.id, [("a.jpg", b"\xff\xd8one")], "kitchen", ag)
    return ag, p, m


def _media_token(client, user) -> str:
    r = client.get("/api/auth/media-token", headers=auth(user))
    assert r.status_code == 200
    body = r.json()
    payload = jwt.decode(body["token"], settings.SECRET_KEY, algorithms=[ALG])
    assert payload["purpose"] == "media" and payload["sub"] == str(user.id)
    assert 0 < body["expires_in"] <= 12 * 3600  # hours, not the session's 72
    return body["token"]


def test_media_token_opens_the_file_by_get(db, client):
    ag, _p, m = _photo(db)
    mt = _media_token(client, ag)
    r = client.get(f"/api/media/{m.path}", params={"token": mt})
    assert r.status_code == 200 and r.content == b"\xff\xd8one"
    assert client.get(f"/api/media/{m.path}", params={"token": mt, "p": 1}).status_code == 200  # the preview too
    # the object's access rules still apply: another agent's media token does not open it
    other = make_user(db, "agent")
    assert client.get(f"/api/media/{m.path}", params={"token": _media_token(client, other)}).status_code == 404


def test_media_token_is_refused_for_api_calls_and_non_get(db, client):
    ag, p, m = _photo(db)
    mt = _media_token(client, ag)
    assert client.get("/api/auth/me", params={"token": mt}).status_code == 401
    assert client.get(f"/api/properties/{p.id}", params={"token": mt}).status_code == 401
    assert client.get("/api/auth/media-token", params={"token": mt}).status_code == 401  # can't renew itself
    assert client.delete(f"/api/properties/{p.id}/media/{m.id}", params={"token": mt}).status_code == 401
    assert client.post(f"/api/media/{m.path}", params={"token": mt}).status_code in (401, 405)
    # not as a bearer either: a media token is not a session
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {mt}"}).status_code == 401
    assert client.get(f"/api/media/{m.path}", headers={"Authorization": f"Bearer {mt}"}).status_code == 401


def test_session_token_in_the_query_is_refused(db, client):
    ag, p, m = _photo(db)
    session = create_token(ag)
    assert client.get(f"/api/media/{m.path}", params={"token": session}).status_code == 401
    assert client.get("/api/auth/me", params={"token": session}).status_code == 401
    assert client.get(f"/api/media/{m.path}", headers=auth(ag)).status_code == 200  # the header keeps working
    # another purpose stays refused anywhere
    other = create_token(ag, purpose="nda")
    assert client.get(f"/api/media/{m.path}", params={"token": other}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {other}"}).status_code == 401


def test_daily_rent_manager_gets_a_media_token_for_its_photos_only(db, client):
    u = make_user(db, "daily_rent_manager")
    storage.put("daily/1/x.jpg", b"\xff\xd8dr")
    storage.put("offers/car/1/y.jpg", b"\xff\xd8car")
    mt = _media_token(client, u)
    assert client.get("/api/media/daily/1/x.jpg", params={"token": mt}).content == b"\xff\xd8dr"
    assert client.get("/api/media/offers/car/1/y.jpg", params={"token": mt}).status_code == 403
