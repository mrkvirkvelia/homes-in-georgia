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
    assert job.payload["phase"] == "warn"  # a day (David 11-22), warned 2 h before
    assert timedelta(hours=21, minutes=59) < job.due_at - datetime.now(timezone.utc) < timedelta(hours=22, minutes=1)
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


def test_calls_without_the_owner_on_board_still_return(db, client, sent):
    """David 11-22: «не дозвонился» / a call alone keeps nothing; the owner confirmed or thinking keeps the object."""
    ag = make_user(db, "agent", "Георгий")
    failed = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7002").id}, headers=auth(ag)).json()["id"]
    r = client.post(f"/api/properties/{failed}/call", json={"reached": False}, headers=auth(ag))
    assert r.status_code == 200 and r.json()["status"] == "call_failed", r.text
    assert client.get(f"/api/properties/{failed}", headers=auth(ag)).json()["idle_return_at"]
    kept = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7004").id, "force": True}, headers=auth(ag)).json()["id"]
    db.get(Property, kept).status = "owner_confirmed"
    db.commit()
    for _ in range(2):
        _due_now(db, failed)
        _due_now(db, kept)
        worker.tick()
    db.expire_all()
    assert db.get(Property, failed).archive_reason == "idle_return"
    assert db.get(Property, kept).agent_id == ag.id
    assert len(sent.of("property_idle_returned")) == 1


def test_setting_changed_after_the_take_replans(db, client, sent):
    ag = make_user(db, "agent", "Георгий")
    settings.set(db, "take_idle_min", "60")
    pid = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7005").id, "force": True}, headers=auth(ag)).json()["id"]
    settings.set(db, "take_idle_min", "1440")
    _due_now(db, pid)
    worker.tick()
    db.expire_all()
    assert db.get(Property, pid).status == "taken" and not sent.of("property_idle_warning")
    job = jobs.pending(db, "take_idle", pid)[0]
    assert job.payload["minutes"] == 1440 and job.due_at - datetime.now(timezone.utc) > timedelta(hours=21)


def test_off_and_manual_objects_never_return(db, client):
    ag = make_user(db, "agent", "Георгий")
    manual = client.post("/api/properties", json={"address": "Ваке 1"}, headers=auth(ag)).json()["id"]
    assert not jobs.pending(db, "take_idle", manual)
    settings.set(db, "take_idle_min", "0")
    pid = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7003").id}, headers=auth(ag)).json()["id"]
    assert not jobs.pending(db, "take_idle", pid)
