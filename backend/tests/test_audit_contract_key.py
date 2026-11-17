"""Audit: the wizard's autosave of a standalone contract with its editing-session key (data._key) is idempotent — a
second first-save sent before the first one returned its id gets the same draft, not a second one."""
from app.models import Contract
from app.services import contracts as C
from tests.conftest import auth, make_user

KEY = "6f1c2a7e-0d4b-4f3a-9a51-2b8e3c1d9f00"


def test_repeated_session_key_returns_the_same_standalone_draft(db, client):
    ag, other = make_user(db, "agent"), make_user(db, "agent")
    h = auth(ag)
    a = client.post("/api/contracts/draft", json={"kind": "rent", "data": {"owner_full_name": "Нино", "_key": KEY}}, headers=h).json()
    b = client.post("/api/contracts/draft", json={"kind": "rent", "data": {"owner_full_name": "Нино Б", "_key": KEY}}, headers=h).json()
    assert b["id"] == a["id"]
    assert b["data"]["owner_full_name"] == "Нино Б"  # the later autosave's data lands in that draft
    assert db.query(Contract).filter(Contract.created_by == ag.id).count() == 1
    # another session (new key / no key) is another contract; the same key of another user is not his draft
    assert client.post("/api/contracts/draft", json={"kind": "rent", "data": {"_key": KEY.replace("6f", "7f")}}, headers=h).json()["id"] != a["id"]
    assert client.post("/api/contracts/draft", json={"kind": "rent", "data": {"x": "1"}}, headers=h).json()["id"] != a["id"]
    assert client.post("/api/contracts/draft", json={"kind": "rent", "data": {"_key": KEY}}, headers=auth(other)).json()["id"] != a["id"]


def test_session_key_alone_does_not_mark_the_pdf_stale(db, client, monkeypatch):
    monkeypatch.setattr(C, "render_pdf", lambda page: b"%PDF-1.4 generated")
    ag = make_user(db, "agent")
    h = auth(ag)
    d = client.post("/api/contracts/draft", json={"kind": "rent", "lang": "RU", "data": {"owner_full_name": "Нино"}}, headers=h).json()
    page = "<!doctype html><html><body><p>x</p></body></html>"
    g = client.put(f"/api/contracts/{d['id']}", json={"kind": "rent", "lang": "RU", "html": page, "data": {"owner_full_name": "Нино"}}, headers=h).json()
    assert g["has_pdf"]
    r = client.post("/api/contracts/draft", json={"id": d["id"], "kind": "rent", "lang": "RU", "data": {"owner_full_name": "Нино", "_key": KEY}}, headers=h).json()
    assert not r["pdf_stale"]
