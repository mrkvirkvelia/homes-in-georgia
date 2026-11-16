"""«Собственник сдал» needs the lease dates; the agent is reminded before the end, then «Освобождаются» → «Снова в работу»."""
from datetime import date, timedelta

from app.models import Property
from app.services import jobs
from tests.conftest import auth, make_listing, make_user


def test_owner_rented_needs_dates_reminds_and_comes_back(db, client, sent):
    david = make_user(db, "agent", "David")
    nino = make_user(db, "operator", "Нино")
    make_listing(db, "ol1")
    pid = client.post("/api/properties", json={"listing_id": "ol1"}, headers=auth(david)).json()["id"]
    url = f"/api/properties/{pid}/rented-self"
    assert client.post(url, json={}, headers=auth(david)).json()["code"] == "lease_dates_required"
    bad = client.post(url, json={"rent_from": "2027-01-01", "rent_to": "2026-12-01"}, headers=auth(david)).json()
    assert bad["code"] == "bad_lease_dates" and db.get(Property, pid).status == "taken"

    end = date.today() + timedelta(days=60)
    r = client.post(url, json={"rent_from": str(date.today()), "rent_to": str(end), "price": "900"}, headers=auth(david)).json()
    assert r["status"] == "archived" and r["archive_reason"] == "rented_by_owner" and r["rent_to"] == str(end)
    assert "900" in r["archive_comment"]
    assert sorted(j.ref for j in jobs.pending(db, "property_lease_expiry")) == [f"{pid}:30", f"{pid}:7"]
    # the calendar (rent_to set) — the agent's own, staff all
    assert pid in {i["id"] for i in client.get("/api/properties?rented=1", headers=auth(david)).json()["items"]}
    assert pid in {i["id"] for i in client.get("/api/properties?rented=1", headers=auth(nino)).json()["items"]}
    assert client.get("/api/properties?freeing=1", headers=auth(david)).json()["total"] == 0

    from app.telegram import notify
    from app.services import users as users_svc
    db.get(Property, pid).rent_to = date.today()
    db.commit()
    assert [i["id"] for i in client.get("/api/properties?freeing=1", headers=auth(david)).json()["items"]] == [pid]
    r = client.post(f"/api/properties/{pid}/resume", headers=auth(david)).json()
    assert r["status"] == "taken" and r["archive_reason"] is None and r["rent_to"] is None and r["agent"]["name"] == "David"
    assert not jobs.pending(db, "property_lease_expiry")
    assert client.get("/api/properties?freeing=1", headers=auth(david)).json()["total"] == 0


def test_archive_owner_rented_needs_dates_and_old_ones_get_them(db, client):
    david = make_user(db, "agent", "David")
    make_listing(db, "ol2")
    pid = client.post("/api/properties", json={"listing_id": "ol2"}, headers=auth(david)).json()["id"]
    url = f"/api/properties/{pid}/archive"
    assert client.post(url, json={"reason": "rented_by_owner"}, headers=auth(david)).json()["code"] == "lease_dates_required"
    # an object archived before the rule (no dates): the card adds them by an edit, the reminders follow
    p = db.get(Property, pid)
    p.status, p.archive_reason = "archived", "rented_by_owner"
    db.commit()
    end = date.today() + timedelta(days=40)
    r = client.patch(f"/api/properties/{pid}", json={"rent_from": str(date.today()), "rent_to": str(end)}, headers=auth(david))
    assert r.status_code == 200 and r.json()["rent_to"] == str(end)
    assert sorted(j.ref for j in jobs.pending(db, "property_lease_expiry")) == [f"{pid}:30", f"{pid}:7"]
