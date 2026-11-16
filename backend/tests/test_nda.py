"""NDA for new agents (services/nda.py): the company signature once, staff make an NDA, the agent confirms himself with
Telegram (Login Widget HMAC; only the named @username), signs, the signed PDF is printed and sent."""
import base64
import hashlib
import hmac
import struct
import time
import zlib

import pytest

from app.models import AgentNda, Job
from app.services import contracts as C, nda as N
from tests.conftest import auth, make_user

PDF = b"%PDF-1.4 nda"


def _png(w=40, h=20) -> str:
    raw = b"".join(b"\x00" + b"\x00\x00\x00\xff" * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)  # noqa: E731
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode()


SIG = _png()


def _widget(**f):
    """A Telegram Login Widget answer signed like Telegram does (key = SHA256(bot token))."""
    f = {"id": "777001", "first_name": "Nino", "username": "nino_agent", "auth_date": str(int(time.time())), **f}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    f["hash"] = hmac.new(hashlib.sha256(b"123456:TEST-TOKEN").digest(), dcs.encode(), hashlib.sha256).hexdigest()
    return f


@pytest.fixture(autouse=True)
def fake_chrome(monkeypatch):
    seen = []
    monkeypatch.setattr(C, "render_pdf", lambda page: seen.append(page) or PDF)
    return seen


@pytest.fixture(autouse=True)
def tg_sent(monkeypatch):
    sent = []
    monkeypatch.setattr(N, "_bg", lambda fn, *a: fn(*a))  # Telegram sends inline in tests
    monkeypatch.setattr(N.httpx, "post", lambda url, **kw: sent.append((url, kw["data"]["chat_id"], kw["files"]["document"][0])))
    return sent


def test_full_flow(db, client, fake_chrome, tg_sent):
    boss, op = make_user(db, "superadmin", tg_id=111), make_user(db, "operator", tg_id=222)
    ag = make_user(db, "agent")
    body = {"lang": "KA-RU", "full_name": "Nino *Test*", "full_name_ka": "ნინო ტესტი", "personal_id": "01001055555",
            "phone": "+995 555 11 22 33", "telegram": "@Nino_Agent", "role": "recruit", "ie": "406112233",
            "address": "Tbilisi, Vake 1", "email": "nino@example.com", "access": "2026-11-20", "iban_gel": "GE00TB0000000000000001"}
    # no company signature yet; only a superadmin sets it; agents can't make NDAs
    assert client.post("/api/ndas", json=body, headers=auth(op)).status_code == 409
    assert client.post("/api/ndas", json={**body, "full_name": "Arthur"}, headers=auth(op)).status_code == 400  # no surname
    assert client.post("/api/ndas", json={**body, "full_name_ka": "Baloyan"}, headers=auth(op)).status_code == 400  # not Georgian
    assert client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(op)).status_code == 403
    assert client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss)).status_code == 200
    assert client.post("/api/ndas", json=body, headers=auth(ag)).status_code == 403
    r = client.post("/api/ndas", json=body, headers=auth(op))
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["status"] == "sent" and n["telegram"] == "Nino_Agent" and n["full_name"] == "Nino Test" and n["role"] == "Агент"  # a «recruit» in the body is ignored: always Агент
    assert n["details"]["level"] == "50" and n["number"].endswith(f"-{n['id']:04d}")
    h = n["html"]
    for s in ("Nino Test", "ნინო ტესტი", "01001055555", "@Nino_Agent", "406112233", "Tbilisi, Vake 1", "nino@example.com",
              "20.11.2026", "GE00TB0000000000000001", n["number"], "326129853", "GE89TB7085336010100094"):
        assert s in h, s
    assert "Участник" in h and "მონაწილე" in h and "русском" in h and "Приложение 5" in h  # two columns, chapter 24, appendices
    assert "{" not in h.split("<body>")[1]  # every field filled
    assert "Роль:" not in h and "присвоены роль" not in h and "Уровень:" not in h  # no role / level in the text
    token = n["path"].split("/")[-1]

    v = client.get(f"/api/public/nda/{token}").json()  # no login
    assert v["confirmed"] is False and v["html"]
    sign = {"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}
    assert client.post(f"/api/public/nda/{token}", json=sign).status_code == 403  # Telegram first
    # a forged / other account's confirmation is refused
    bad = _widget()
    bad["hash"] = "0" * 64
    assert client.post(f"/api/public/nda/{token}/telegram", json=bad).status_code == 401
    assert client.post(f"/api/public/nda/{token}/telegram", json=_widget(username="someone_else")).status_code == 403
    assert client.post(f"/api/public/nda/{token}/telegram", json={"test": True}).status_code == 401  # not the test server
    r = client.post(f"/api/public/nda/{token}/telegram", json=_widget())
    assert r.status_code == 200 and r.json()["confirmed"] and r.json()["tg_username"] == "nino_agent"
    assert client.post(f"/api/public/nda/{token}", json={**sign, "consent": False}).status_code == 400
    assert client.post(f"/api/public/nda/{token}", json={**sign, "doc_sha256": "x" * 64}).status_code == 409

    r = client.post(f"/api/public/nda/{token}", json=sign, headers={"x-forwarded-for": "9.9.9.9", "user-agent": "UA-nda"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "signed" and r.json()["html"] is None and r.json()["has_pdf"]
    page = fake_chrome[-1]
    assert page.count(f'<img src="{SIG}"') == 6  # company + agent in both language tables, + both on the record page
    assert "9.9.9.9" in page and "UA-nda" in page and "777001" in page and "Протокол электронного подписания" in page
    assert "[эл. подпись]" not in page
    # sent to the staff member who made it and to the agent; Drive queued
    assert {chat for _, chat, _ in tg_sent} == {"222", "777001"}
    assert db.query(Job).filter_by(kind="nda_drive", ref=str(n["id"])).count() == 1
    assert client.get(f"/api/public/nda/{token}/pdf").content == PDF
    assert client.get(f"/api/ndas/{n['id']}/pdf", headers=auth(op)).content == PDF
    assert client.post(f"/api/public/nda/{token}", json=sign).status_code == 409  # once
    lst = client.get("/api/ndas", headers=auth(op)).json()
    assert lst["total"] == 1 and lst["items"][0]["status_label"] == "Подписано"


def test_any_account_when_no_username_cancel_and_languages(db, client):
    boss = make_user(db, "superadmin")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    for lang, needle, absent in (("KA", "მონაწილე", "Участник"), ("KA-EN", "Participant", "Участник")):
        n = client.post("/api/ndas", json={"lang": lang, "full_name": "A Test", "personal_id": "1"}, headers=auth(boss)).json()
        assert needle in n["html"] and absent not in n["html"] and n["role"] == "Агент" and n["details"]["level"] == "50"
        assert ("ინგლისურ" in n["html"]) == (lang == "KA-EN")  # chapter 24 «Language»: bilingual only
    n = client.post("/api/ndas", json={"lang": "KA", "full_name": "A Test", "personal_id": "1"}, headers=auth(boss)).json()
    token = n["path"].split("/")[-1]
    assert client.post(f"/api/public/nda/{token}/telegram", json=_widget(username="whoever")).status_code == 200
    assert client.post(f"/api/ndas/{n['id']}/cancel", headers=auth(boss)).json()["status"] == "cancelled"
    assert client.get(f"/api/public/nda/{token}").status_code == 404
    assert client.post("/api/ndas", json={"lang": "XX", "full_name": "A Test", "personal_id": "1"}, headers=auth(boss)).status_code == 400


def test_test_mode_confirmation_and_pdf_retry(db, client, monkeypatch):
    from app import worker
    from app.services.errors import DomainError
    boss = make_user(db, "superadmin")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    n = client.post("/api/ndas", json={"iban_gel": "GE00TB0000000000000001", "lang": "KA-EN", "full_name": "B Test", "personal_id": "2", "telegram": "b_agent"},
                    headers=auth(boss)).json()
    token = n["path"].split("/")[-1]
    monkeypatch.setattr(N, "_test_mode", lambda: True)
    v = client.post(f"/api/public/nda/{token}/telegram", json={"test": True}).json()
    assert v["confirmed"] and v["tg_username"] == "b_agent"

    def boom(page):
        raise DomainError("pdf_failed", "x", 502)
    monkeypatch.setattr(C, "render_pdf", boom)
    r = client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]})
    assert r.status_code == 200 and r.json()["status"] == "signed" and not r.json()["has_pdf"]
    job = db.query(Job).filter_by(kind="nda_pdf", ref=str(n["id"])).one()
    monkeypatch.setattr(C, "render_pdf", lambda page: PDF)
    assert worker.run_job(db, job) == "ok"
    db.expire_all()
    assert db.get(AgentNda, n["id"]).pdf_path


def test_edit_text(db, client):
    """An admin changes this NDA's clauses while unsigned (like a client contract's text): new text + hash, an open
    signing page must reload; operators can't; a signed NDA is frozen; null → the standard text back."""
    boss, op = make_user(db, "superadmin", tg_id=111), make_user(db, "operator", tg_id=222)
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    n = client.post("/api/ndas", json={"lang": "KA-RU", "full_name": "Nino Test", "personal_id": "01001055555"},
                    headers=auth(op)).json()
    t = client.get(f"/api/ndas/{n['id']}/text", headers=auth(op)).json()
    assert t["edited"] is False and t["edition"] == N.EDITION
    blocks = t["blocks"]
    i = next(i for i, b in enumerate(blocks) if b["k"] == "n")
    blocks[i] = {**blocks[i], "ka": "ახალი ტექსტი {pid} {oops", "todo": ["ru", "en", "xx"]}
    blocks.insert(i + 1, {"k": "n", "n": "0.9", "ka": "<b>დამატებითი</b>", "ru": "Особое условие", "en": ""})
    del blocks[i + 2]
    body = {"blocks": blocks}
    assert client.put(f"/api/ndas/{n['id']}/text", json=body, headers=auth(op)).status_code == 403
    pv = client.post(f"/api/ndas/{n['id']}/text/preview", json=body, headers=auth(boss)).json()["html"]
    assert "Особое условие" in pv and client.get(f"/api/ndas/{n['id']}", headers=auth(op)).json()["html"] == n["html"]
    r = client.put(f"/api/ndas/{n['id']}/text", json=body, headers=auth(boss))
    assert r.status_code == 200, r.text
    h = r.json()["html"]
    assert "ახალი ტექსტი <b>01001055555</b> {oops" in h and "Особое условие" in h and "&lt;b&gt;დამატებითი" in h
    t = client.get(f"/api/ndas/{n['id']}/text", headers=auth(op)).json()
    assert t["edited"] and t["blocks"][i]["todo"] == ["ru", "en"] and len(t["blocks"]) == len(blocks)
    token = n["path"].split("/")[-1]
    v = client.get(f"/api/public/nda/{token}").json()
    assert v["html"] == h
    assert v["doc_sha256"] == hashlib.sha256(h.encode()).hexdigest()
    assert client.put(f"/api/ndas/{n['id']}/text", json={"blocks": [{"k": "script"}]}, headers=auth(boss)).status_code == 400
    # back to the standard text
    r = client.put(f"/api/ndas/{n['id']}/text", json={"blocks": None}, headers=auth(boss)).json()
    assert r["html"] == n["html"] and "blocks" not in r["details"]
    # signed: frozen
    row = db.get(AgentNda, n["id"])
    row.status = "signed"
    db.commit()
    assert client.put(f"/api/ndas/{n['id']}/text", json=body, headers=auth(boss)).status_code == 409


def test_ie_number_from_profile(db, client, fake_chrome, tg_sent):
    """ИП in the profile (Stanislav 11-16): required for field users (badge / cabinet), never blocks a save; an NDA made
    for a user takes it; a signed NDA without it gets an amended PDF (original kept), an unsigned one is re-rendered."""
    boss = make_user(db, "superadmin", tg_id=111)
    ag = make_user(db, "agent", username="Nino_Agent", first_name="Nino", last_name="B", phone="+995555112233",
                   email="n@x.ge")
    from datetime import date
    ag.birth_date = date(1990, 1, 1)
    db.commit()
    assert client.get("/api/auth/me", headers=auth(ag)).json()["profile_missing"] == ["ie_number"]
    assert "ie_number" not in client.get("/api/auth/me", headers=auth(boss)).json()["profile_missing"]
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    body = {"iban_gel": "GE00TB0000000000000001", "lang": "KA-RU", "full_name": "Nino B", "personal_id": "01001055555", "telegram": "nino_agent"}
    signed = client.post("/api/ndas", json=body, headers=auth(boss)).json()
    assert signed["details"]["ie"] == ""
    token = signed["path"].split("/")[-1]
    client.post(f"/api/public/nda/{token}/telegram", json=_widget())
    v = client.get(f"/api/public/nda/{token}").json()
    assert client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}).status_code == 200
    unsigned = client.post("/api/ndas", json=body, headers=auth(boss)).json()
    old_hash = client.get(f"/api/public/nda/{unsigned['path'].split('/')[-1]}").json()["doc_sha256"]
    original = db.get(AgentNda, signed["id"]).html
    tg_sent.clear()

    assert client.patch("/api/auth/me", json={"ie_number": "12ab"}, headers=auth(ag)).status_code == 400
    r = client.patch("/api/auth/me", json={"ie_number": "010 0105 5555"}, headers=auth(ag))
    assert r.status_code == 200 and r.json()["ie_number"] == "01001055555" and r.json()["profile_missing"] == []
    db.expire_all()
    s = db.get(AgentNda, signed["id"])
    assert s.html == original and s.pdf_path and s.details.get("ie") is None or s.details.get("ie") == ""  # signed text kept
    am = s.details["ie_amended"]
    assert am["ie"] == "01001055555" and am["pdf"] != s.pdf_path
    page = fake_chrome[-1]
    assert "Дополнение: реквизиты участника" in page and "01001055555" in page and "Номер ИП внесён" in page
    assert client.get(f"/api/ndas/{s.id}/pdf?amended=true", headers=auth(boss)).content == PDF
    assert [chat for _, chat, _ in tg_sent] == ["777001"]
    u = db.get(AgentNda, unsigned["id"])
    assert "01001055555" in u.html and u.doc_sha256 != old_hash and u.status == "sent"
    # saving the same number again changes nothing; a new NDA for him is prefilled
    tg_sent.clear()
    client.patch("/api/auth/me", json={"ie_number": "01001055555"}, headers=auth(ag))
    assert tg_sent == []
    assert client.post("/api/ndas", json=body, headers=auth(boss)).json()["details"]["ie"] == "01001055555"


def test_ie_from_signed_nda_to_profile(db, client):
    boss = make_user(db, "superadmin")
    ag = make_user(db, "agent", tg_id=777001)
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    n = client.post("/api/ndas", json={"iban_gel": "GE00TB0000000000000001", "full_name": "N Test", "personal_id": "1", "ie": "406112233"}, headers=auth(boss)).json()
    token = n["path"].split("/")[-1]
    client.post(f"/api/public/nda/{token}/telegram", json=_widget())
    v = client.get(f"/api/public/nda/{token}").json()
    client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]})
    db.expire_all()
    assert db.get(type(ag), ag.id).ie_number == "406112233"


def test_team_without_nda_prefill_send_and_writeback(db, client, monkeypatch):
    """Team members without a signed agreement: listed with what's missing, the form prefilled from the profile, one open
    agreement each (409 → «Пересоздать»), the link sent by the CRM bot, bulk only for complete profiles, the personal
    number written back on signing."""
    from app.telegram import client as tg
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text, kb=None, **kw: sent.append((chat, kb)) or (None if chat == 999 else {"ok": 1}))
    boss = make_user(db, "superadmin")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    nino = make_user(db, "agent", first_name="Nino", last_name="Beridze", tg_id=777001, username="nino_agent", level=70,
                     phone="+995 555 1", email="n@x.ge", ie_number="406112233")
    gio = make_user(db, "recruit", first_name="Gio", last_name="K", tg_id=999, personal_id="01001000001")
    make_user(db, "recruit", first_name="Old", deleted_at=N.now())  # removed: not listed
    make_user(db, "operator")  # not a field user
    r = client.get("/api/ndas/team", headers=auth(boss)).json()
    rows = {x["user_id"]: x for x in r["items"]}
    assert set(rows) == {nino.id, gio.id} and r["signed"] == 0
    assert not rows[nino.id]["ready"] and "personal_id" in rows[nino.id]["missing"] and rows[gio.id]["ready"]
    p = rows[nino.id]["prefill"]
    assert p["full_name"] == "Nino Beridze" and p["telegram"] == "@nino_agent" and p["level"] == "70" and p["ie"] == "406112233"
    assert p["role"] == "agent"
    assert rows[gio.id]["prefill"]["role"] == "agent" and rows[gio.id]["prefill"]["level"] == "50"

    # bulk: only Gio (complete profile); the bot can't write to him → «скопируйте ссылку»
    assert client.post("/api/ndas/team/send-all", headers=auth(boss)).json() == {"made": 1, "sent": 0, "not_sent": [gio.name]}
    assert client.post("/api/ndas/team/send-all", headers=auth(boss)).json()["made"] == 0  # no duplicates

    # Nino: the admin fills the personal number; a second one is refused unless «Пересоздать»
    body = {**p, "personal_id": "01001055555"}
    n1 = client.post("/api/ndas", json=body, headers=auth(boss)).json()
    assert n1["user_id"] == nino.id and n1["details"]["ie"] == "406112233"
    assert client.post("/api/ndas", json=body, headers=auth(boss)).status_code == 409
    n2 = client.post("/api/ndas", json={**body, "replace": True}, headers=auth(boss)).json()
    # after a cancel the form comes back with what was typed (not only the profile)
    row = {x["user_id"]: x for x in client.get("/api/ndas/team", headers=auth(boss)).json()["items"]}[nino.id]
    assert row["prefill"]["personal_id"] == "01001055555" and row["prefill"]["full_name"] == "Nino Beridze"
    assert client.get(f"/api/ndas/{n1['id']}", headers=auth(boss)).json()["status"] == "cancelled"
    s = client.post(f"/api/ndas/{n2['id']}/send", headers=auth(boss)).json()
    assert s["sent"] and s["url"].endswith(n2["path"]) and sent[-1][0] == 777001
    assert sent[-1][1]["inline_keyboard"][0][0]["url"] == s["url"]
    row = {x["user_id"]: x for x in client.get("/api/ndas/team", headers=auth(boss)).json()["items"]}[nino.id]
    assert row["status"] == "sent" and row["nda"]["id"] == n2["id"]

    # signed → off the list, the personal number in the profile
    token = n2["path"].split("/")[-1]
    client.post(f"/api/public/nda/{token}/telegram", json=_widget())
    v = client.get(f"/api/public/nda/{token}").json()
    # the agent's own details on the signing page: an IBAN is required, ИП optional; the text is re-rendered
    sig = {"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}
    assert client.post(f"/api/public/nda/{token}", json=sig).status_code == 400
    assert client.post(f"/api/public/nda/{token}/details", json={"iban_gel": "", "iban_usd": ""}).status_code == 400
    assert client.post(f"/api/public/nda/{token}/details", json={"iban_gel": "GE12 nope"}).status_code == 400
    v2 = client.post(f"/api/public/nda/{token}/details", json={"iban_usd": "ge29 tb00 0000 0000 0000 01", "ie": "406112233"}).json()
    assert v2["details"] == {"iban_gel": "", "iban_usd": "GE29TB0000000000000001", "ie": "406112233"}
    assert v2["doc_sha256"] != v["doc_sha256"] and "GE29TB0000000000000001" in v2["html"]
    v = v2
    assert client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}).status_code == 200
    db.expire_all()
    assert db.get(type(nino), nino.id).personal_id == "01001055555"
    assert db.get(type(nino), nino.id).iban_usd == "GE29TB0000000000000001"
    r = client.get("/api/ndas/team", headers=auth(boss)).json()
    assert [x["user_id"] for x in r["items"]] == [gio.id] and r["signed"] == 1
    assert client.get("/api/ndas/team", headers=auth(nino)).status_code == 403


def test_confirm_in_login_bot(db, client, monkeypatch):
    """«Подтвердить в Telegram-боте»: /start nda_<token> in the CRM sign-in bot confirms the sender (only the named
    @username), the page then lets him sign; the bot answers with a link back to the page."""
    from app.telegram import login_bot
    sent = []
    monkeypatch.setattr(login_bot, "call", lambda method, **kw: sent.append(kw) or {"ok": 1})
    boss = make_user(db, "superadmin")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    n = client.post("/api/ndas", json={"full_name": "Nino Test", "personal_id": "1", "telegram": "@nino_agent",
                                       "iban_gel": "GE00TB0000000000000001"}, headers=auth(boss)).json()
    token = n["path"].split("/")[-1]
    upd = lambda uname: {"message": {"text": f"/start nda_{token}", "chat": {"id": 5, "type": "private"},  # noqa: E731
                                     "from": {"id": 777001, "username": uname, "first_name": "Nino"}}}
    assert "@nino_agent" in login_bot.handle(upd("someone_else")) and not client.get(f"/api/public/nda/{token}").json()["confirmed"]
    assert "Подтверждено" in login_bot.handle(upd("Nino_Agent"))
    assert sent[-1]["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(n["path"])
    v = client.get(f"/api/public/nda/{token}").json()
    assert v["confirmed"] and v["tg_username"] == "Nino_Agent"
    r = client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]})
    assert r.status_code == 200 and r.json()["status"] == "signed"
    assert "⚠️" in login_bot.handle(upd("Nino_Agent"))  # signed: no second confirmation


def test_correct_signed(db, client):
    """«Исправить» a signed agreement: a new one for the same member (supersedes), the signed one stays in force until the
    correction is signed, then it is marked superseded; only a signed one can be corrected."""
    boss = make_user(db, "superadmin")
    ag = make_user(db, "agent", first_name="Nino", last_name="B", tg_id=777001, username="nino_agent")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    body = {"full_name": "Nino Typo", "personal_id": "1", "telegram": "@nino_agent", "iban_gel": "GE00TB0000000000000001",
            "user_id": ag.id}

    def sign(n):
        token = n["path"].split("/")[-1]
        client.post(f"/api/public/nda/{token}/telegram", json=_widget())
        v = client.get(f"/api/public/nda/{token}").json()
        assert client.post(f"/api/public/nda/{token}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}).status_code == 200
    old = client.post("/api/ndas", json=body, headers=auth(boss)).json()
    assert client.post("/api/ndas", json={**body, "supersedes": old["id"], "replace": True}, headers=auth(boss)).status_code == 409  # not signed yet
    sign(old)
    new = client.post("/api/ndas", json={**body, "full_name": "Nino Beridze", "supersedes": old["id"], "replace": True}, headers=auth(boss)).json()
    assert new["details"]["supersedes"] == old["id"]
    assert "superseded_by" not in client.get(f"/api/ndas/{old['id']}", headers=auth(boss)).json()["details"]  # in force meanwhile
    sign(new)
    assert client.get(f"/api/ndas/{old['id']}", headers=auth(boss)).json()["details"]["superseded_by"] == new["id"]


def test_common_template_editions(db, client):
    """Admins edit the common text: a new edition (1.3 → 1.4) with who / which clauses; only NEW NDAs use it, a sent one
    keeps its text until re-generated (blocks null), a signed one never changes; back to the original text = 1.5."""
    boss, op = make_user(db, "superadmin", tg_id=111), make_user(db, "operator", tg_id=222)
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    old = client.post("/api/ndas", json={"lang": "KA-RU", "full_name": "Old One", "personal_id": "1"}, headers=auth(op)).json()
    assert old["edition"] == N.EDITION and f"Редакция {N.EDITION}" in old["html"]
    t = client.get("/api/ndas/template", headers=auth(op)).json()
    assert t["edition"] == N.EDITION and t["default"] and t["next"] == "1.4"
    blocks = t["blocks"]
    i = next(i for i, b in enumerate(blocks) if b["k"] == "n" and b["n"] == "1.2")
    blocks[i] = {**blocks[i], "ru": "Новый общий пункт"}
    tab = next(b for b in blocks if b["k"] == "t")
    tab["rows"][0][0] = {**tab["rows"][0][0], "ru": "Ячейка изменена"}
    body = {"blocks": blocks, "base": N.EDITION}
    assert client.put("/api/ndas/template", json=body, headers=auth(op)).status_code == 403
    pv = client.post("/api/ndas/template/preview", json={**body, "lang": "KA-RU", "edition": "1.4"}, headers=auth(boss)).json()
    assert "Новый общий пункт" in pv["html"] and "Редакция 1.4" in pv["html"]
    r = client.put("/api/ndas/template", json=body, headers=auth(boss))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["edition"] == "1.4" and t["history"][0]["changes"] == ["1.2", "таблица"] and t["history"][0]["by_name"]
    assert client.put("/api/ndas/template", json=body, headers=auth(boss)).status_code == 409  # base 1.3 is stale
    new = client.post("/api/ndas", json={"lang": "KA-RU", "full_name": "New One", "personal_id": "2"}, headers=auth(op)).json()
    assert new["edition"] == "1.4" and "Новый общий пункт" in new["html"] and "Ячейка изменена" in new["html"]
    assert "Редакция 1.4" in new["html"] and "· 1.4 ·" in new["html"]
    # the sent one keeps 1.3 …
    o = client.get(f"/api/ndas/{old['id']}", headers=auth(op)).json()
    assert o["html"] == old["html"] and o["edition"] == N.EDITION
    assert client.get(f"/api/ndas/{old['id']}/text", headers=auth(op)).json()["current"] == "1.4"
    # … until an admin re-generates it
    o = client.put(f"/api/ndas/{old['id']}/text", json={"blocks": None}, headers=auth(boss)).json()
    assert o["edition"] == "1.4" and "Новый общий пункт" in o["html"]
    # back to the original text: a new edition, the code text
    t = client.put("/api/ndas/template", json={"blocks": None, "base": "1.4"}, headers=auth(boss)).json()
    assert t["edition"] == "1.5" and t["blocks"] == N.BLOCKS and t["history"][0]["from"] == N.EDITION
    t = client.put("/api/ndas/template", json={"from_edition": "1.4", "edition": "2.0"}, headers=auth(boss)).json()
    assert t["edition"] == "2.0" and t["blocks"][i]["ru"] == "Новый общий пункт"
    bad = client.put("/api/ndas/template", json={"blocks": None, "edition": "1.4"}, headers=auth(boss))
    assert bad.status_code == 400
    # a signed NDA is never re-generated
    row = db.get(AgentNda, new["id"])
    row.status = "signed"
    db.commit()
    assert client.put(f"/api/ndas/{new['id']}/text", json={"blocks": None}, headers=auth(boss)).status_code == 409
    assert db.get(AgentNda, new["id"]).html == new["html"]


def test_new_nda_latest_edition_sent_keeps_own(db, client):
    """A new NDA takes the latest common edition; a sent one keeps its own text and edition, even when re-rendered with
    the agent's IBAN on the signing page (Stanislav 11-17)."""
    boss = make_user(db, "superadmin", tg_id=111)
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    sent = client.post("/api/ndas", json={"full_name": "Sent One", "personal_id": "1"}, headers=auth(boss)).json()
    blocks = client.get("/api/ndas/template", headers=auth(boss)).json()["blocks"]
    i = next(i for i, b in enumerate(blocks) if b["k"] == "n")
    blocks[i] = {**blocks[i], "ru": "Пункт новой редакции"}
    assert client.put("/api/ndas/template", json={"blocks": blocks}, headers=auth(boss)).json()["edition"] == "1.4"
    new = client.post("/api/ndas", json={"full_name": "New One", "personal_id": "2"}, headers=auth(boss)).json()
    assert new["edition"] == "1.4" and new["details"]["edition"] == "1.4" and "Пункт новой редакции" in new["html"]
    token = sent["path"].split("/")[-1]
    r = client.post(f"/api/public/nda/{token}/details", json={"iban_gel": "GE00TB0000000000000001"})
    assert r.status_code == 200, r.text
    s = client.get(f"/api/ndas/{sent['id']}", headers=auth(boss)).json()
    assert s["edition"] == N.EDITION and "GE00TB0000000000000001" in s["html"] and "Пункт новой редакции" not in s["html"]
    assert f"Редакция {N.EDITION}" in s["html"]
