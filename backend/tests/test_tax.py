"""«Декларации RS.ge» (Irakli 11-24, services/tax.py): the agent types the month's turnover from his bank statement,
sees the 1 % tax, marks it filed; staff see the team; Telegram reminds the ones who haven't filed."""
from datetime import date, datetime

from app import worker
from app.models import Job, TaxDeclaration
from app.services import tax
from app.services.common import TZ, now
from app.telegram.notify import tax_reminder_text  # imported before the `sent` fixture stubs notify.*
from tests.conftest import auth, make_user

DAY = date(2026, 11, 10)


def _day(monkeypatch, d=DAY):
    monkeypatch.setattr(tax, "today", lambda: d)


def test_periods_and_deadline():
    assert tax.due_period(date(2026, 11, 10)) == date(2026, 10, 1)
    assert tax.due_period(date(2026, 1, 3)) == date(2025, 12, 1)
    assert tax.deadline(date(2025, 12, 1)) == date(2026, 1, 15)
    assert tax.deadline(date(2026, 2, 1)) == date(2026, 3, 15)
    assert float(tax.tax_of("1234.55")) == 12.35  # half up


def test_agent_enters_and_files(db, client, monkeypatch):
    _day(monkeypatch)
    ag = make_user(db, "agent", ie_number="01001012345", tg_id=501)
    h = auth(ag)

    me = client.get("/api/me/tax", headers=h).json()
    cur = me["current"]
    assert me["has_ie"] and me["rs_url"].startswith("https://")
    assert (cur["period"], cur["deadline"], cur["status"], cur["days_left"], cur["overdue"]) == \
        ("2026-10", "2026-11-15", "missing", 5, False)
    assert len(me["history"]) == 12 and me["history"][-1]["period"] == "2025-11"

    r = client.put("/api/me/tax/2026-10", headers=h, json={"turnover": 4520.5})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["turnover"], r.json()["tax"]) == ("entered", 4520.5, 45.21)

    r = client.put("/api/me/tax/2026-10", headers=h, json={"turnover": 4520.5, "filed": True, "note": " TBC "})
    assert r.json()["status"] == "filed" and r.json()["filed_at"] and r.json()["note"] == "TBC"
    filed_at = r.json()["filed_at"]
    # saving again keeps the first filing time; unticking clears it
    assert client.put("/api/me/tax/2026-10", headers=h, json={"turnover": 4600, "filed": True}).json()["filed_at"] == filed_at
    assert client.put("/api/me/tax/2026-10", headers=h, json={"turnover": 4600}).json()["status"] == "entered"
    assert db.query(TaxDeclaration).count() == 1

    # zero is a valid declaration; the current (unfinished) month and nonsense are not
    assert client.put("/api/me/tax/2026-09", headers=h, json={"turnover": 0, "filed": True}).json()["status"] == "filed"
    assert client.put("/api/me/tax/2026-11", headers=h, json={"turnover": 1}).status_code == 400
    assert client.put("/api/me/tax/2026-13", headers=h, json={"turnover": 1}).status_code == 400
    assert client.put("/api/me/tax/2026-10", headers=h, json={"turnover": -1}).status_code == 422


def test_overdue_after_the_15th(db, client, monkeypatch):
    _day(monkeypatch, date(2026, 11, 16))
    ag = make_user(db, "agent", ie_number="123456789")
    cur = client.get("/api/me/tax", headers=auth(ag)).json()["current"]
    assert cur["overdue"] and cur["days_left"] == -1
    # older months without a record are not «просрочена»: the agent may not have used the page yet
    assert not any(d["overdue"] for d in client.get("/api/me/tax", headers=auth(ag)).json()["history"][1:])


def test_access(db, client, monkeypatch):
    _day(monkeypatch)
    ag, other, op = make_user(db, "agent", ie_number="01001012345"), make_user(db, "agent"), make_user(db, "operator")
    # no ИП number → can't save, the cabinet says so
    assert client.get("/api/me/tax", headers=auth(other)).json()["has_ie"] is False
    r = client.put("/api/me/tax/2026-10", headers=auth(other), json={"turnover": 10})
    assert r.status_code == 400 and "ИП" in r.text
    # agents never see each other's; staff read anyone's and the team overview
    assert client.get(f"/api/me/tax?user_id={ag.id}", headers=auth(other)).status_code == 403
    assert client.get(f"/api/me/tax?user_id={ag.id}", headers=auth(op)).status_code == 200
    assert client.get("/api/tax/overview", headers=auth(ag)).status_code == 403


def test_overview(db, client, monkeypatch):
    _day(monkeypatch)
    a1, a2 = make_user(db, "agent", name="Аня", ie_number="01001012345"), make_user(db, "agent", name="Бека", ie_number="123456789")
    make_user(db, "recruit", name="Вано")  # no ИП
    make_user(db, "agent", name="Гела", ie_number="111111111", is_active=False)  # not working: not listed
    op = make_user(db, "operator")
    client.put("/api/me/tax/2026-10", headers=auth(a1), json={"turnover": 1000, "filed": True})
    client.put("/api/me/tax/2026-10", headers=auth(a2), json={"turnover": 200})

    ov = client.get("/api/tax/overview", headers=auth(op)).json()
    assert ov["period"] == "2026-10" and ov["deadline"] == "2026-11-15"
    by = {r["user"]["name"]: r for r in ov["rows"]}
    assert set(by) == {"Аня", "Бека", "Вано"}
    assert (by["Аня"]["status"], by["Аня"]["tax"]) == ("filed", 10.0)
    assert (by["Бека"]["status"], by["Вано"]["has_ie"]) == ("entered", False)
    assert ov["totals"] == {"people": 2, "filed": 1, "entered": 1, "missing": 0, "no_ie": 1}
    assert client.get("/api/tax/overview?period=2026-09", headers=auth(op)).json()["totals"]["missing"] == 2


def test_reminder_schedule_and_recipients(db, sent):
    assert tax.next_reminder(datetime(2026, 11, 1, 9, 0, tzinfo=TZ)) == date(2026, 11, 1)
    assert tax.next_reminder(datetime(2026, 11, 1, 11, 0, tzinfo=TZ)) == date(2026, 11, 10)
    assert tax.next_reminder(datetime(2026, 11, 14, 12, 0, tzinfo=TZ)) == date(2026, 12, 1)

    tax.ensure_job(db)
    tax.ensure_job(db)
    assert db.query(Job).filter(Job.kind == "tax_reminder").count() == 1

    day = now().astimezone(TZ).date()
    p = tax.due_period(day)
    todo = make_user(db, "agent", name="Должен", ie_number="01001012345", tg_id=601)
    done = make_user(db, "agent", name="Подал", ie_number="123456789", tg_id=602)
    half = make_user(db, "agent", name="Внёс", ie_number="223456789", tg_id=603)
    make_user(db, "agent", name="Без ИП", tg_id=604)
    make_user(db, "agent", name="Без Telegram", ie_number="323456789")
    db.add_all([TaxDeclaration(user_id=done.id, period=p, turnover=100, filed_at=now()),
                TaxDeclaration(user_id=half.id, period=p, turnover=100)])
    db.commit()

    worker.tax_reminder(db, Job(kind="tax_reminder", ref=day.isoformat(), due_at=now(), payload={}))
    got = {u.name: d["status"] for u, d in sent.of("tax_reminder")}
    assert got == {"Должен": "missing", "Внёс": "entered"} and todo.id
    # a day the worker missed is not sent late
    sent.clear()
    assert worker.tax_reminder(db, Job(kind="tax_reminder", ref="2020-01-01", due_at=now(), payload={})) == "stale"
    assert sent.of("tax_reminder") == []


def test_reminder_text():
    entered = tax.out(date(2026, 10, 1), TaxDeclaration(turnover=4520.5), date(2026, 11, 10))
    txt = tax_reminder_text(entered)
    assert "за октябрь 2026" in txt and "до 15 ноября" in txt and "осталось 5 дн." in txt
    assert "4 520.50 ₾" in txt and "45.21 ₾" in txt
    txt = tax_reminder_text(tax.out(date(2026, 10, 1), None, date(2026, 11, 15)))
    assert "сегодня последний день" in txt and "банковской выписки" in txt
