"""§12 «Бизнес-процесс эксклюзива» (David 11-19): an exclusive without the e-signature passes by itself when its
duplicate search finds nothing; with duplicates it waits 24 h for the contract and the other ads taken down, then is
searched again — clean → approved, dirty → the operator decides; never approved by the system with duplicates left."""
import json
from datetime import timedelta

from app import worker
from app.models import ChangeRequest, Event, Job, Listing, Property
from app.services import jobs, properties, similar
from app.services.common import now
from tests.conftest import auth, make_listing, make_user
from tests.test_exclusive_contract import JPG
from tests.test_similar import H, _object


def _exclusive(db, client, agent):
    pid = _object(db, client, agent)
    db.get(Property, pid).is_exclusive = True  # straight in the row: no «exclusive» search of its own before the request
    db.commit()
    return pid


def _ask(client, pid, agent, scan=False):
    r = client.post(f"/api/properties/{pid}/exclusive-no-esign", data={"reason": "собственник за границей"},
                    files={"file": ("paper.jpg", JPG)} if scan else None, headers=auth(agent))
    assert r.status_code == 200, r.text
    return r.json()["no_esign"]["id"]


def _twin(db):  # a competitor's ad with two of the object's photos, re-uploaded
    make_listing(db, "mh7001", source="myhome", urls=json.dumps(["https://myhome.ge/7001"]), address="Kazbegi 30",
                 photo_hashes=json.dumps([H[0] ^ 1, H[1]]), text="Сдаю")


def _due_now(db, kind="dup_recheck"):
    for j in db.query(Job).filter_by(kind=kind, done_at=None):
        j.due_at = now() - timedelta(seconds=1)
    db.commit()


def _gates(sent):
    return [a[1] for a in sent.of("exclusive_dups_gate")]


def test_no_duplicates_pass_by_themselves(db, client, sent):
    ag = make_user(db, "agent", "Вика")
    pid = _exclusive(db, client, ag)
    rid = _ask(client, pid, ag)
    assert jobs.pending(db, "dup_scan", pid)[0].payload == {"trigger": "no_esign"}
    worker.tick()
    db.expire_all()
    w = db.get(ChangeRequest, rid)
    assert (w.status, w.decided_by, w.decision_comment) == ("approved", None, "Эксклюзив подтверждён: дублей нет")
    assert properties.contract_done(db, db.get(Property, pid))
    assert _gates(sent) == ["clear"] and not sent.of("exclusive_duplicates")
    assert db.query(Event).filter_by(entity_id=str(pid), action="exclusive_dups_clear").count() == 1
    card = client.get(f"/api/properties/{pid}", headers=auth(ag)).json()
    assert card["no_esign"]["dups"]["state"] == "clear" and "эксклюзивный договор (PDF)" not in card["missing"]
    assert not jobs.pending(db, "dup_recheck", pid)


def test_duplicates_wait_24h_then_the_operator_decides(db, client, sent):
    ag, op = make_user(db, "agent", "Вика"), make_user(db, "operator", "Нино")
    pid = _exclusive(db, client, ag)
    _twin(db)
    rid = _ask(client, pid, ag)
    worker.tick()
    db.expire_all()
    w = db.get(ChangeRequest, rid)
    d = w.payload["dups"]
    assert w.status == "pending" and d["state"] == "waiting" and not d["received"]
    assert [(x["key"], x["level"]) for x in d["items"]] == [("l:mh7001", "confirmed")]
    assert d["items"][0]["url"] == "https://myhome.ge/7001" and "общих фото: 2" in d["items"][0]["reasons"]
    (job,) = jobs.pending(db, "dup_recheck", pid)
    assert timedelta(hours=23, minutes=59) < job.due_at - now() <= timedelta(hours=24)
    (prop, state, items, deadline), = sent.of("exclusive_dups_gate")
    assert prop.id == pid and state == "waiting" and items[0]["listing_id"] == "mh7001" and deadline
    assert not sent.of("exclusive_duplicates")  # one message, the list in it

    # repeated scans (photos, new ads, a re-run): no new message, no second job, the state stays
    similar.scan_exclusive(db, pid, "media")
    similar.scan_exclusive(db, pid, "new_ads")
    similar.scan_exclusive(db, pid, "exclusive")
    assert len(sent.of("exclusive_dups_gate")) == 1 and len(jobs.pending(db, "dup_recheck", pid)) == 1
    assert db.get(ChangeRequest, rid).payload["dups"]["state"] == "waiting"

    # the operator's queue and the card show it
    q = client.get("/api/change-requests", headers=auth(op)).json()["items"]
    assert q[0]["dups"]["state"] == "waiting" and q[0]["dups"]["deadline"] == d["deadline"]
    assert client.get(f"/api/properties/{pid}", headers=auth(ag)).json()["no_esign"]["dups"]["state"] == "waiting"

    # 24 h later the ad is still there: the operator decides, nothing is approved
    _due_now(db)
    worker.tick()
    db.expire_all()
    w = db.get(ChangeRequest, rid)
    assert w.status == "pending" and w.payload["dups"]["state"] == "operator"
    assert _gates(sent) == ["waiting", "operator"]
    assert db.get(Listing, "mh7001").status == "published"  # never removed by the system
    # the job again (a restart, a retry): a no-op
    assert similar.scan_exclusive(db, pid, "dup_recheck")["gate"] is None and len(sent.of("exclusive_dups_gate")) == 2
    # the operator may still approve by hand
    r = client.post(f"/api/change-requests/{rid}/decide", json={"approve": True}, headers=auth(op))
    assert r.json()["status"] == "approved"


def test_recheck_clean_with_the_contract_is_allowed(db, client, sent):
    ag = make_user(db, "agent", "Вика")
    pid = _exclusive(db, client, ag)
    _twin(db)
    rid = _ask(client, pid, ag, scan=True)  # the paper contract is attached
    worker.tick()
    assert db.get(ChangeRequest, rid).payload["dups"]["state"] == "waiting"
    # the owner had the other ad taken down
    db.get(Listing, "mh7001").status = "gone"
    db.commit()
    _due_now(db)
    worker.tick()
    db.expire_all()
    w = db.get(ChangeRequest, rid)
    assert w.status == "approved" and w.payload["dups"]["state"] == "clear" and w.payload["dups"]["received"]
    assert _gates(sent) == ["waiting", "clear"]
    assert not jobs.pending(db, "dup_recheck", pid)


def test_recheck_clean_without_the_contract_goes_to_the_operator(db, client, sent):
    ag = make_user(db, "agent")
    pid = _exclusive(db, client, ag)
    _twin(db)
    rid = _ask(client, pid, ag)
    worker.tick()
    db.get(Listing, "mh7001").status = "gone"
    db.commit()
    _due_now(db)
    worker.tick()
    db.expire_all()
    assert db.get(ChangeRequest, rid).status == "pending"
    assert db.get(ChangeRequest, rid).payload["dups"]["state"] == "operator"


def test_doubtful_matches_go_to_review_not_blocked(db, client, sent, monkeypatch):
    ag = make_user(db, "agent")
    pid = _exclusive(db, client, ag)
    _twin(db)
    monkeypatch.setattr(similar, "dup_level", lambda item: "doubtful")  # the % scoring's lowest band
    rid = _ask(client, pid, ag)
    worker.tick()
    db.expire_all()
    w = db.get(ChangeRequest, rid)
    assert w.status == "pending" and w.payload["dups"]["state"] == "review"
    assert not jobs.pending(db, "dup_recheck", pid) and _gates(sent) == ["review"]


def test_dup_level_adapter():
    assert similar.dup_level({"level": "same"}) == "confirmed"
    assert similar.dup_level({"level": "maybe", "decided": "same"}) == "confirmed"
    assert similar.dup_level({"level": "maybe"}) == "probable"
    assert similar.dup_level({"level": "probable"}) == "probable"
    assert similar.dup_level({"level": "doubtful"}) == "doubtful"
