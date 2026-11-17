"""Audit fixes: a failed Telegram send in a worker job is retried / recorded (not «ok»), secrets stay out of the logs,
the test suite refuses to wipe a database that is not a test one."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import update

from app import worker
from app.models import Job
from app.services import jobs
from app.services.common import now
from app.telegram import client as tg
from app.telegram import notify
from tests.conftest import auth, make_listing, make_user

REAL_NOTIFY = dict(vars(notify))  # module import time: before the autouse `sent` fixture stubs notify.*


@pytest.fixture
def real_notify(monkeypatch):
    for k, v in REAL_NOTIFY.items():
        if getattr(notify, k, None) is not v:
            monkeypatch.setattr(notify, k, v)


class R:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class Http:
    """A fake Bot API: fail(chat) -> None (ok) | "down" | "5xx" | "429" | "blocked" | "not_found"."""
    def __init__(self, fail=lambda chat: None):
        self.calls, self.fail = [], fail

    def post(self, url, data=None, files=None):
        chat = str((data or {}).get("chat_id"))
        self.calls.append((url.rsplit("/", 1)[-1], chat))
        f = self.fail(chat)
        if f == "down":
            raise httpx.ConnectError("connection refused")
        if f == "5xx":
            return R(502, {"ok": False, "error_code": 502, "description": "Bad Gateway"})
        if f == "429":
            return R(429, {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 1}})
        if f == "blocked":
            return R(403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
        if f == "not_found":
            return R(400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
        return R(200, {"ok": True, "result": {"message_id": len(self.calls), "chat": {"id": int(chat)}}})

    def chats(self):
        return [c for _, c in self.calls]


@pytest.fixture
def http(monkeypatch):
    h = Http()
    monkeypatch.setattr(tg, "_client", lambda: h)
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)  # the 429 wait
    return h


@notify.safe
def fan_out(chats):
    for c in chats:
        tg.send(c, f"hello {c}")


def _job(db, kind, ref="1", **payload):
    job = Job(kind=kind, ref=ref, due_at=now(), payload=payload)
    db.add(job)
    db.commit()
    return job


def _rerun(db, job):
    """The retry is due now (the backoff moved due_at into the future)."""
    db.execute(update(Job).where(Job.id == job.id).values(due_at=now() - timedelta(seconds=1)))
    db.commit()
    return worker.run_job(db, db.get(Job, job.id, populate_existing=True))


@pytest.mark.parametrize("fail", ["down", "5xx", "429", "blocked", "not_found"])
def test_outside_a_job_a_failed_send_is_still_none(http, fail):
    """API requests and the bot: unchanged, a failed send is None and nothing raises (no business logic breaks)."""
    http.fail = lambda chat: fail
    assert tg.send(1, "x") is None
    assert fan_out([1, 2]) is None and http.chats().count("2") >= 1


@pytest.mark.parametrize("fail,permanent", [("down", False), ("5xx", False), ("429", False), ("blocked", True), ("not_found", True)])
def test_inside_a_job_transient_raises_permanent_is_recorded(http, fail, permanent):
    http.fail = lambda chat: fail
    with tg.delivery() as d:
        if permanent:
            assert tg.send(1, "x") is None  # the handler goes on (other recipients still get theirs)
        else:
            with pytest.raises(tg.DeliveryError):
                tg.send(1, "x")
            with pytest.raises(tg.DeliveryError):  # through notify.safe too
                fan_out([1])
    assert d.failed and d.failed[0].permanent is permanent
    with tg.delivery():
        http.fail = lambda chat: "not_found"
        assert tg.call("editMessageText", chat_id=1, message_id=1, text="x") is None  # edits/deletes never raise


def test_transient_failure_retries_with_backoff_without_resending(db, http, monkeypatch):
    monkeypatch.setitem(worker.HANDLERS, "t_fan", lambda db, job: fan_out([1, 2, 3]))
    http.fail = lambda chat: "down" if chat == "2" else None
    job = _job(db, "t_fan")
    assert worker.run_job(db, job) == "error"
    job = db.get(Job, job.id, populate_existing=True)
    assert job.done_at is None and job.attempts == 1 and job.due_at > now() + timedelta(minutes=1)
    assert job.last_error.startswith("DeliveryError: telegram sendMessage to 2")
    assert http.chats() == ["1", "2"]  # stopped at the failure: 3 is not sent yet
    http.calls.clear()
    http.fail = lambda chat: None
    assert _rerun(db, job) == "ok"
    assert http.chats() == ["2", "3"]  # 1 already had its message: not sent twice
    job = db.get(Job, job.id, populate_existing=True)
    assert job.done_at and job.last_error is None and "_tg_sent" not in job.payload and "_due_at" not in job.payload


def test_transient_failure_gives_up_after_max_attempts(db, http, monkeypatch):
    monkeypatch.setitem(worker.HANDLERS, "t_fan", lambda db, job: fan_out([1]))
    http.fail = lambda chat: "5xx"
    job = _job(db, "t_fan")
    for _ in range(worker.MAX_ATTEMPTS):
        assert _rerun(db, job) == "error"
    job = db.get(Job, job.id, populate_existing=True)
    assert job.done_at and job.attempts == worker.MAX_ATTEMPTS and "502" in job.last_error


def test_blocked_recipient_finishes_the_job_undelivered_others_get_it(db, http, monkeypatch):
    monkeypatch.setitem(worker.HANDLERS, "t_fan", lambda db, job: fan_out([1, 2, 3]))
    http.fail = lambda chat: "blocked" if chat == "2" else None
    job = _job(db, "t_fan")
    assert worker.run_job(db, job) == "undelivered"
    job = db.get(Job, job.id, populate_existing=True)
    assert http.chats() == ["1", "2", "3"]
    assert job.done_at and job.attempts == 1  # finished: no retry of a refusal
    assert job.last_error.startswith("not delivered: telegram sendMessage to 2: 403 Forbidden: bot was blocked")


def test_best_effort_notice_keeps_the_state_change(db, http, monkeypatch):
    """take_idle / lead_sla warning: the next phase is planned even when the notice can't go out."""
    def handler(db, job):
        worker._best_effort(fan_out, [1])
        jobs.schedule(db, "t_next", 1, now() + timedelta(hours=1))
    monkeypatch.setitem(worker.HANDLERS, "t_fan", handler)
    http.fail = lambda chat: "down"
    job = _job(db, "t_fan")
    assert worker.run_job(db, job) == "undelivered"
    job = db.get(Job, job.id, populate_existing=True)
    assert job.done_at and "ConnectError" in job.last_error and jobs.pending(db, "t_next", 1)


def test_owner_followup_retry_is_not_stale(db, client, http, real_notify):
    """A retry moves due_at; the «did the date move?» check compares the planned time, so the retry still sends."""
    david = make_user(db, "agent", "David", tg_id=4242)
    make_listing(db, "au1")
    pid = client.post("/api/properties", json={"listing_id": "au1"}, headers=auth(david)).json()["id"]
    client.post(f"/api/properties/{pid}/owner", json={"is_owner": True, "owner_name": "Rezi", "owner_phone": "+995 597 44 44 03"},
                headers=auth(david))
    client.post(f"/api/properties/{pid}/thinking", json={"until": datetime.now(timezone.utc).isoformat()}, headers=auth(david))
    job = jobs.pending(db, "owner_followup", pid)[0]
    http.fail = lambda chat: "down"
    assert worker.run_job(db, job) == "error"
    http.calls.clear()
    http.fail = lambda chat: None
    assert _rerun(db, job) == "ok"
    assert http.chats() == ["4242"]


# --- access tokens stay out of the logs -------------------------------------------------------------------------------

TOK = "Zx9_secretTOKEN-abcdefghij0123"


def _lines(caplog, logger):
    return [r for r in caplog.records if r.name == logger]


@pytest.mark.parametrize("method,url,route", [
    ("GET", f"/api/public/esign/{TOK}", "/api/public/esign/{token}"),
    ("GET", f"/api/public/esign/{TOK}/pdf", "/api/public/esign/{token}/pdf"),
    ("POST", f"/api/public/nda/{TOK}/details", "/api/public/nda/{token}/details"),
    ("GET", f"/api/public/contracts/{TOK}/pdf", "/api/public/contracts/{token}/pdf"),
    ("GET", f"/api/public/exclusive/{TOK}", "/api/public/exclusive/{token}"),
    ("GET", f"/api/public/ics/{TOK}", "/api/public/ics/{token}"),
    ("GET", f"/api/public/daily-rent/ical/{'ab' * 24}.ics", "/api/public/daily-rent/ical/{file}"),
    ("GET", f"/api/auth/invite/{TOK}", "/api/auth/invite/{token}"),
    ("GET", f"/api/no-such-route/{TOK}", None),  # no route: masked by shape
])
def test_request_log_never_has_the_token(client, caplog, method, url, route):
    caplog.set_level("INFO", logger="app.request")
    secret = url.rsplit("/", 1)[-1] if route and "{file}" in route else TOK
    r = client.request(method, url, json={} if method == "POST" else None)
    assert r.status_code >= 400
    rec = _lines(caplog, "app.request")[-1]
    assert secret not in rec.getMessage() and secret not in json.dumps(rec.fields, default=str)
    assert rec.fields["route"] == route and "***" in rec.fields["path"] and rec.fields["method"] == method


def test_request_log_keeps_ids(db, client, caplog):
    caplog.set_level("INFO", logger="app.request")
    u = make_user(db, "agent", "Ivy")
    client.get("/api/leads/987654", headers=auth(u))
    rec = _lines(caplog, "app.request")[-1]
    assert rec.fields["path"] == "/api/leads/987654" and rec.fields["route"] == "/api/leads/{lead_id}"


def test_client_log_masks_token_urls(client, caplog):
    caplog.set_level("INFO", logger="app.client")
    r = client.post("/api/client-log", json={
        "kind": "onerror", "message": f"fetch https://admin.hge.ge/api/public/nda/{TOK}/pdf?x=1 failed",
        "url": f"https://admin.hge.ge/esign/{TOK}?tgWebAppData=user%3D1#frag", "api_path": f"GET /public/esign/{TOK}/pdf",
        "stack": f"Error\n    at https://admin.hge.ge/assets/index-abc.js:1:2 (/sign/{TOK})"})
    assert r.json() == {"ok": True}
    rec = _lines(caplog, "app.client")[-1]
    dump = json.dumps(rec.fields, ensure_ascii=False) + rec.getMessage()
    assert TOK not in dump and "tgWebAppData" not in dump and "frag" not in dump
    assert rec.fields["url"] == "https://admin.hge.ge/esign/***" and rec.fields["api_path"] == "GET /public/esign/***/pdf"
    assert "index-abc.js:1:2" in rec.fields["stack"]


# --- the test suite never wipes a database that is not a test one ------------------------------------------------------

@pytest.mark.parametrize("test_url,main_url,ok", [
    ("postgresql+psycopg://homes:homes@homes-ci-db:5432/homes_test", None, True),  # deploy/autodeploy.sh
    ("postgresql+psycopg://postgres@127.0.0.1:5544/homes_test_b", "postgresql+psycopg://homes:x@127.0.0.1:5544/homes", True),
    ("postgresql://postgres@/homes_test?host=/tmp/pg", "postgresql://postgres@/homes?host=/tmp/pg", True),
    ("postgresql+psycopg://homes:homes@db:5432/homes", None, False),  # the prod database name
    ("postgresql+psycopg://homes:homes@db/homes_test", "postgresql://other:pw@db:5432/homes_test", False),  # = DATABASE_URL
])
def test_conftest_refuses_a_non_test_database(test_url, main_url, ok):
    from tests.conftest import check_test_db
    if ok:
        check_test_db(test_url, main_url)
    else:
        with pytest.raises(RuntimeError, match="TEST_DATABASE_URL"):
            check_test_db(test_url, main_url)
