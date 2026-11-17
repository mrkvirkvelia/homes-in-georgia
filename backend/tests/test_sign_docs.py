"""«Документ на подпись» (services/sign_docs.py): a draft with the pasted text → sent (company signature, links) → every
signer signs on the NDA's signing page (Telegram for team members) → signed, the PDF has the pasted text, and nothing
changes after that."""
import pytest

from app.models import Job
from app.services import contracts as C, nda as N
from app.telegram import client as tgc, login_bot
from tests.conftest import auth, make_user
from tests.test_nda import PDF, SIG, _widget

BODY_KA = "1. ხელშეკრულების საგანი.\nპირველი ხაზი\n\n2. მხარეთა <b>ვალდებულებები</b> **მნიშვნელოვანი**"
BODY_RU = "1. Предмет договора.\nВторая строка\n\n2. Обязанности сторон <script>x</script>\n\n3. Срок действия"


@pytest.fixture(autouse=True)
def fake_chrome(monkeypatch):
    seen = []
    monkeypatch.setattr(C, "render_pdf", lambda page: seen.append(page) or PDF)
    return seen


@pytest.fixture(autouse=True)
def tg_sent(monkeypatch):
    sent, links = [], []
    monkeypatch.setattr(N, "_bg", lambda fn, *a: fn(*a))
    monkeypatch.setattr(N.httpx, "post", lambda url, **kw: sent.append((url, kw["data"]["chat_id"], kw["files"]["document"][0])))
    monkeypatch.setattr(tgc, "send", lambda chat, text, kb=None, **kw: links.append((chat, kb)) or {"message_id": 1})
    return sent


def _doc(member, cosigner=None, lang="KA-RU"):
    return {"lang": lang, "title": {"ka": "მომსახურების ხელშეკრულება", "ru": "Договор оказания услуг"},
            "body": {"ka": BODY_KA, "ru": BODY_RU}, "party": {"user_id": member.id, "personal_id": "01001099999"},
            "cosigner": {"user_id": cosigner.id} if cosigner else None}


def test_create_sign_immutable(db, client, fake_chrome, tg_sent):
    boss, op = make_user(db, "superadmin", tg_id=111), make_user(db, "operator", name="Ирина Оператор", tg_id=222)
    nino = make_user(db, "agent", name="Nino", first_name="Nino", last_name="Beridze", phone="+995 555 000 111",
                     tg_id=777001, username="nino_agent")
    assert client.post("/api/sign-docs", json=_doc(nino), headers=auth(nino)).status_code == 403  # staff only
    assert client.post("/api/sign-docs", json={**_doc(nino), "body": {"ka": BODY_KA}}, headers=auth(op)).status_code == 400

    r = client.post("/api/sign-docs", json=_doc(nino, cosigner=op), headers=auth(op))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "draft" and d["number"] == f"D-{d['created_at'][:4]}-{d['id']:04d}" and d["editable"]
    party = next(s for s in d["signers"] if s["side"] == "party")
    assert party["full_name"] == "Nino Beridze" and party["phone"] == "+995 555 000 111" and party["need_tg"] and not party["path"]
    h = d["html"]
    for s in ("Договор оказания услуг", "მომსახურების ხელშეკრულება", "Предмет договора.<br>Вторая строка", "Срок действия",
              "<b>მნიშვნელოვანი</b>", "&lt;script&gt;", "Nino Beridze", "01001099999", "326129853", "Ирина Оператор", d["number"]):
        assert s in h, s
    assert "<script>" not in h and "Сторона 2" in h and "მხარე 2" in h

    # editable as a draft; no company signature → can't send
    upd = {**_doc(nino, cosigner=op), "body": {"ka": BODY_KA, "ru": BODY_RU + "\n\n4. Новый пункт"}}
    assert "4. Новый пункт" in client.put(f"/api/sign-docs/{d['id']}", json=upd, headers=auth(op)).json()["html"]
    assert client.post(f"/api/sign-docs/{d['id']}/send", headers=auth(op)).status_code == 409
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    r = client.post(f"/api/sign-docs/{d['id']}/send", headers=auth(op))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "sent" and all(x["sent"] for x in d["links"])  # both are in Telegram: the CRM bot sent the links
    tok = {s["side"]: s["path"].split("/")[-1] for s in d["signers"]}
    assert client.get(f"/api/public/doc/{'x' * 32}").status_code == 404

    v = client.get(f"/api/public/doc/{tok['party']}").json()
    assert v["need_tg"] and not v["confirmed"] and "4. Новый пункт" in v["html"]
    sign = {"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]}
    assert client.post(f"/api/public/doc/{tok['party']}", json=sign).status_code == 403  # Telegram first
    assert client.post(f"/api/public/doc/{tok['party']}/telegram", json=_widget(id="999", username="nino_agent")).status_code == 403
    assert client.post(f"/api/public/doc/{tok['party']}/telegram", json=_widget()).json()["confirmed"]
    # still editable before the first signature: the text changes, the open page must reload
    upd["body"]["ru"] += "\n\n5. Последний пункт"
    assert client.put(f"/api/sign-docs/{d['id']}", json=upd, headers=auth(op)).status_code == 200
    assert client.post(f"/api/public/doc/{tok['party']}", json=sign).status_code == 409  # doc_changed
    v = client.get(f"/api/public/doc/{tok['party']}").json()
    sign["doc_sha256"] = v["doc_sha256"]
    r = client.post(f"/api/public/doc/{tok['party']}", json=sign, headers={"x-forwarded-for": "9.9.9.9"})
    assert r.status_code == 200 and r.json()["signed"] and r.json()["status"] == "sent"  # waiting for our second signer
    # one signature in → the text is frozen
    assert client.put(f"/api/sign-docs/{d['id']}", json=upd, headers=auth(op)).status_code == 409

    # our second signer confirms in the CRM sign-in bot (/start sd_<token>) and signs
    frm = {"id": 222, "username": "irina", "first_name": "Ирина"}
    assert "Подтверждено" in login_bot.handle({"message": {"text": f"/start sd_{tok['company']}", "from": frm,
                                                           "chat": {"id": 222, "type": "private"}}})
    assert client.get(f"/api/public/doc/{tok['company']}").json()["confirmed"]
    r = client.post(f"/api/public/doc/{tok['company']}", json=sign)
    assert r.status_code == 200 and r.json()["status"] == "signed" and r.json()["has_pdf"] and r.json()["html"] is None

    page = fake_chrome[-1]  # the signed PDF: the pasted text, every signature, the record
    assert "5. Последний пункт" in page and "ხელშეკრულების საგანი" in page and "Протокол электронного подписания" in page
    assert page.count(f'<img src="{SIG}"') == 6 and "[эл. подпись]" not in page and "9.9.9.9" in page and "777001" in page
    assert {chat for _, chat, _ in tg_sent} == {"222", "777001"}  # the author (= cosigner here) and Nino
    assert db.query(Job).filter_by(kind="sign_doc_drive", ref=str(d["id"])).count() == 1
    assert client.get(f"/api/public/doc/{tok['party']}/pdf").content == PDF
    assert client.get(f"/api/sign-docs/{d['id']}/pdf", headers=auth(op)).content == PDF

    # signed = immutable
    assert client.put(f"/api/sign-docs/{d['id']}", json=upd, headers=auth(op)).status_code == 409
    assert client.post(f"/api/sign-docs/{d['id']}/cancel", headers=auth(op)).status_code == 409
    assert client.post(f"/api/public/doc/{tok['party']}", json=sign).status_code == 409
    lst = client.get("/api/sign-docs", params={"status": "signed", "q": "Beridze"}, headers=auth(op)).json()
    assert lst["total"] == 1 and lst["items"][0]["status_label"] == "Подписан"
    assert client.get("/api/sign-docs", params={"q": "нет такого"}, headers=auth(op)).json()["total"] == 0


def test_outside_person_one_language_cancel(db, client, fake_chrome):
    boss = make_user(db, "superadmin")
    client.put("/api/ndas/company-signature", json={"signature": SIG}, headers=auth(boss))
    base = {"lang": "RU", "title": {"ru": "Договор купли-продажи"}, "body": {"ru": "Первый абзац\n\nВторой абзац"},
            "party": {"full_name": "Иван Петров", "personal_id": "PASS 123"}}
    assert client.post("/api/sign-docs", json=base, headers=auth(boss)).status_code == 400  # an outsider needs a phone
    d = client.post("/api/sign-docs", json={**base, "party": {**base["party"], "phone": "+7 900 000"}}, headers=auth(boss)).json()
    assert "<p>Первый абзац</p><p>Второй абзац</p>" in d["html"] and "მხარე" not in d["html"]  # Russian only
    d = client.post(f"/api/sign-docs/{d['id']}/send", headers=auth(boss)).json()
    assert d["links"] == [{"id": d["signers"][0]["id"], "sent": False}]  # an outsider: staff copy the link
    tok = d["signers"][0]["path"].split("/")[-1]
    v = client.get(f"/api/public/doc/{tok}").json()
    assert not v["need_tg"]  # no Telegram for an outside person without a @username
    r = client.post(f"/api/public/doc/{tok}", json={"signature": SIG, "consent": True, "doc_sha256": v["doc_sha256"]})
    assert r.json()["status"] == "signed" and "Второй абзац" in fake_chrome[-1]

    d2 = client.post("/api/sign-docs", json={**base, "party": {**base["party"], "phone": "1"}}, headers=auth(boss)).json()
    d2 = client.post(f"/api/sign-docs/{d2['id']}/send", headers=auth(boss)).json()
    tok2 = d2["signers"][0]["path"].split("/")[-1]
    assert client.post(f"/api/sign-docs/{d2['id']}/cancel", headers=auth(boss)).json()["status"] == "cancelled"
    assert client.get(f"/api/public/doc/{tok2}").status_code == 404
