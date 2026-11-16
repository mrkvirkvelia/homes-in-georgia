"""Stanislav 11-16: «В архив» → «Дубль» deletes the object; its leads / deals move to the original, posts and files go."""
from app import storage, worker
from app.models import Deal, Event, Lead, Property, PropertyMedia
from app.services import properties
from app.services.common import now_text as now_text_
from tests.conftest import auth, make_client, make_listing
from tests.test_publish_card import _submitted
from tests.test_tg_unpost import _posts


def test_duplicate_is_deleted_and_its_lead_and_deal_move(db, client, monkeypatch):
    deleted = _posts(monkeypatch)
    gone = []
    monkeypatch.setattr(storage, "delete", gone.append)
    georgiy, nino, pid, media = _submitted(db, client)
    properties.publish(db, pid, nino)
    orig = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7001").id}, headers=auth(georgiy)).json()["id"]
    c = make_client(db)
    lead = Lead(client_id=c.id, property_id=pid, created_at=now_text_(), updated_at=now_text_())
    db.add(lead)
    db.flush()
    db.add(Deal(property_id=pid, lead_id=lead.id))
    db.commit()
    paths = set(db.scalars(PropertyMedia.__table__.select().with_only_columns(PropertyMedia.path)
                           .where(PropertyMedia.property_id == pid)))

    r = client.post(f"/api/properties/{pid}/archive", json={"reason": "duplicate", "duplicate_of": orig}, headers=auth(nino)).json()
    assert (r["status"], r["archive_reason"]) == ("archived", "duplicate")
    worker.tick()
    db.expire_all()
    assert db.get(Property, pid) is None
    assert db.get(Lead, lead.id).property_id == orig and db.query(Deal).filter_by(property_id=orig).count() == 1
    assert deleted and set(gone) == paths
    ev = {e.action: e for e in db.query(Event).filter(Event.entity == "property")}
    assert ev["deleted_as_duplicate"].data["original"] == orig and ev["deleted_as_duplicate"].actor_id == nino.id
    assert ev["duplicate_merged"].entity_id == str(orig) and ev["duplicate_merged"].data["moved"]["leads"] == 1


def test_exclusive_duplicate_is_refused(db, client):
    georgiy, nino, pid, _ = _submitted(db, client)
    orig = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7002").id}, headers=auth(georgiy)).json()["id"]
    db.get(Property, pid).is_exclusive = True
    db.commit()
    r = client.post(f"/api/properties/{pid}/archive", json={"reason": "duplicate", "duplicate_of": orig}, headers=auth(nino)).json()
    assert r["code"] == "dup_has_contract" and db.get(Property, pid) is not None
