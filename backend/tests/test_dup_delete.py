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


def _media(db, pid, kind, path):
    db.add(PropertyMedia(property_id=pid, kind=kind, path=path, position=0))
    db.commit()


def test_exclusive_duplicate_hands_its_contract_to_the_original(db, client, monkeypatch):
    _posts(monkeypatch)
    gone = []
    monkeypatch.setattr(storage, "delete", gone.append)
    georgiy, nino, pid, _ = _submitted(db, client)
    orig = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7002").id}, headers=auth(georgiy)).json()["id"]
    db.get(Property, pid).is_exclusive = True
    _media(db, pid, properties.CONTRACT, "properties/x/contract.pdf")
    _media(db, pid, properties.OWNER_ID_DOC, "private/x/id.jpg")
    r = client.post(f"/api/properties/{pid}/archive", json={"reason": "duplicate", "duplicate_of": orig}, headers=auth(nino)).json()
    assert (r["status"], r["archive_reason"]) == ("archived", "duplicate")
    worker.tick()
    db.expire_all()
    assert db.get(Property, pid) is None
    o = db.get(Property, orig)
    assert o.is_exclusive and properties.contract(db, orig).path == "properties/x/contract.pdf"
    assert set(properties.owner_docs(db, orig)) == {properties.OWNER_ID_DOC}
    assert "properties/x/contract.pdf" not in gone and "private/x/id.jpg" not in gone


def test_duplicate_refused_when_both_have_a_contract(db, client):
    georgiy, nino, pid, _ = _submitted(db, client)
    orig = client.post("/api/properties", json={"listing_id": make_listing(db, "ss7003").id}, headers=auth(georgiy)).json()["id"]
    db.get(Property, pid).is_exclusive = True
    _media(db, pid, properties.CONTRACT, "properties/x/a.pdf")
    _media(db, orig, properties.CONTRACT, "properties/y/b.pdf")
    r = client.post(f"/api/properties/{pid}/archive", json={"reason": "duplicate", "duplicate_of": orig}, headers=auth(nino)).json()
    assert r["code"] == "dup_has_contract" and db.get(Property, pid) is not None
