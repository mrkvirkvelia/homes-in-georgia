from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app import worker
from app.models import Job, Property
from app.services import jobs, settings
from tests.conftest import auth, make_listing, make_user


def _due_now(db, pid):
    db.execute(update(Job).where(Job.kind == "take_idle", Job.ref == str(pid), Job.done_at.is_(None))
               .values(due_at=datetime.now(timezone.utc)))
    db.commit()


def test_taken_with_no_action_goes_back_to_the_feed(db, client, sent):
    ag, other = make_user(db, "agent", "Георгий"), make_user(db, "agent", "Леван")
    listing = make_listing(db, "ss7001")
    pid = client.post("/api/properties", json={"listing_id": listing.id}, headers=auth(ag)).json()["id"]
    job = jobs.pending(db, "take_idle", pid)[0]
    assert job.payload["phase"] == "warn"
    assert timedelta(minutes=44) < job.due_at - datetime.now(timezone.utc) < timedelta(minutes=46)
    assert client.get(f"/api/properties/{pid}", headers=auth(ag)).json()["idle_return_at"]
    assert client.get("/api/listings/new", headers=auth(other)).json()["total"] == 0

    _due_now(db, pid)
    worker.tick()
    assert sent.of("property_idle_warning")
    _due_now(db, pid)
    worker.tick()
    assert sent.of("property_idle_returned")
    db.expire_all()
    p = db.get(Property, pid)
    assert p.status == "archived" and p.archive_reason == "idle_return" and p.agent_id is None
    assert client.get("/api/listings/new", headers=auth(other)).json()["total"] == 1
    # someone else takes it: the same object, a fresh timer
    r = client.post("/api/properties", json={"listing_id": listing.id}, headers=auth(other)).json()
    assert r["id"] == pid and r["status"] == "taken" and jobs.pending(db, "take_idle", pid)


def test_any_action_keeps_the_object(db, client, sent):
    ag = make_user(db, "agent", "Георгий")
    pid = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7002").id}, headers=auth(ag)).json()["id"]
    client.post(f"/api/properties/{pid}/call", json={"reached": True}, headers=auth(ag))  # call_reached, still «Взят»
    assert client.get(f"/api/properties/{pid}", headers=auth(ag)).json()["idle_return_at"] is None
    _due_now(db, pid)
    worker.tick()
    db.expire_all()
    assert db.get(Property, pid).agent_id == ag.id and not sent.of("property_idle_warning")


def test_off_and_manual_objects_never_return(db, client):
    ag = make_user(db, "agent", "Георгий")
    manual = client.post("/api/properties", json={"address": "Ваке 1"}, headers=auth(ag)).json()["id"]
    assert not jobs.pending(db, "take_idle", manual)
    settings.set(db, "take_idle_min", "0")
    pid = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7003").id}, headers=auth(ag)).json()["id"]
    assert not jobs.pending(db, "take_idle", pid)
