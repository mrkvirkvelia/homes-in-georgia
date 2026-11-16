"""Stanislav 11-16: «Оператор авто» sees only the cars; a removed (inactive) user is hidden and his objects go to the
platform, deals stay; an avatar can be uploaded (admin for anyone, the employee for himself)."""
import io

from PIL import Image

from app.models import Deal, Property, User
from tests.conftest import auth, make_user


def test_car_operator_sees_only_cars(db, client):
    op = make_user(db, "car_operator", "Гога")
    h = auth(op)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    r = client.post("/api/offers/car", json={"title": "Toyota Prius 2015", "price": 9000, "deal": "rent"}, headers=h)
    assert r.status_code == 200, r.text
    assert client.get("/api/offers/car", headers=h).status_code == 200
    for path in ("/api/properties", "/api/leads", "/api/users", "/api/contracts", "/api/settings"):
        assert client.get(path, headers=h).status_code == 403, path
    # and the Daily Rent operator still can't see the cars
    dr = make_user(db, "daily_rent_manager", "Нино")
    assert client.get("/api/offers/car", headers=auth(dr)).status_code == 403


def test_remove_inactive_user(db, client):
    admin = make_user(db, "admin", "Иракли")
    gone = make_user(db, "agent", "Omari")
    p = Property(address="Казбеги 1", agent_id=gone.id, status="taken")
    db.add(p)
    db.add(Deal(agent_id=gone.id, status="confirmed"))
    db.commit()
    h = auth(admin)
    assert client.delete(f"/api/users/{gone.id}", headers=h).status_code == 409  # active: deactivate first
    gone.is_active = False
    db.commit()
    assert client.delete(f"/api/users/{gone.id}", headers=auth(make_user(db, "operator", "Нино"))).status_code == 403
    r = client.delete(f"/api/users/{gone.id}", headers=h)
    assert r.status_code == 200 and r.json()["objects_to_platform"] == 1
    db.expire_all()
    assert db.get(Property, p.id).agent_id is None
    assert db.query(Deal).filter(Deal.agent_id == gone.id).count() == 1  # the history stays
    assert gone.id not in [u["id"] for u in client.get("/api/users", headers=h).json()["items"]]
    boss = make_user(db, "superadmin", "Давид2")
    boss.is_active = False
    db.commit()
    assert client.delete(f"/api/users/{boss.id}", headers=h).status_code == 403


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 300), (30, 60, 120)).save(out, "PNG")
    return out.getvalue()


def test_avatar_upload(db, client):
    admin = make_user(db, "admin", "Иракли")
    agent = make_user(db, "agent", "Заза")
    other = make_user(db, "agent", "Тамара")
    r = client.post(f"/api/users/{agent.id}/photo", files={"file": ("a.png", _png(), "image/png")}, headers=auth(agent))
    assert r.status_code == 200, r.text
    assert r.json()["photo_url"].startswith(f"/api/media/avatars/u{agent.id}-")
    assert client.post(f"/api/users/{agent.id}/photo", files={"file": ("a.png", _png(), "image/png")}, headers=auth(other)).status_code == 403
    assert client.post(f"/api/users/{other.id}/photo", files={"file": ("a.png", _png(), "image/png")}, headers=auth(admin)).status_code == 200
    assert client.post(f"/api/users/{other.id}/photo", files={"file": ("a.txt", b"hello", "text/plain")}, headers=auth(admin)).status_code == 400
    assert db.get(User, agent.id) is not None
