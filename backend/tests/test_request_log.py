"""Stanislav 11-16: every CRM error findable in the server log — one JSON line per API request, secrets/phones masked,
X-Request-Id back to the browser; frontend errors arrive through /api/client-log."""
import json
import logging

from app import logs
from tests.conftest import auth, make_user


def lines(caplog, name):
    return [r for r in caplog.records if r.name == name]


def test_request_line_and_masking(db, client, caplog):
    caplog.set_level(logging.INFO)
    u = make_user(db, "agent", "Гиорги")
    r = client.get("/api/auth/me", headers=auth(u))
    assert r.status_code == 200 and len(r.headers["X-Request-Id"]) == 10
    rec = lines(caplog, "app.request")[-1]
    f = rec.fields
    assert (f["rid"], f["user_id"], f["user"], f["role"], f["status"]) == (r.headers["X-Request-Id"], u.id, "Гиорги", "agent", 200)
    # a failed login: the body is logged, the password is not
    caplog.clear()
    r = client.post("/api/auth/login", json={"login": "nobody", "password": "hunter2", "phone": "+995 555 12 34 56"})
    assert r.status_code == 401
    f = lines(caplog, "app.request")[-1].fields
    assert f["status"] == 401 and f["error"]["code"] and "hunter2" not in f["body"] and "555 12" not in f["body"]
    line = logs.JsonFormatter("api").format(lines(caplog, "app.request")[-1])
    assert json.loads(line)["status"] == 401 and "hunter2" not in line
    # no token in the logged query
    caplog.clear()
    client.get("/api/auth/me", params={"token": "secret.jwt.value", "q": "x"})
    f = lines(caplog, "app.request")[-1].fields
    assert f["query"] == {"q": "x"}


def test_unhandled_exception_logged_with_traceback(db, client, caplog):
    from fastapi.testclient import TestClient
    from app.main import app

    def boom():
        raise RuntimeError("kaboom")
    app.add_api_route("/api/test-boom", boom)
    app.router.routes.insert(0, app.router.routes.pop())  # before the SPA catch-all
    caplog.set_level(logging.INFO)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/test-boom")
    assert r.status_code == 500 and r.json()["request_id"] == r.headers["X-Request-Id"]
    rec = lines(caplog, "app.request")[-1]
    assert rec.levelname == "ERROR" and "kaboom" in logs.JsonFormatter("api").format(rec)


def test_client_log(db, client, caplog):
    caplog.set_level(logging.INFO)
    u = make_user(db, "operator", "Нино")
    r = client.post("/api/client-log", headers=auth(u), json={"kind": "react", "message": "TypeError: x is undefined",
                                                              "stack": "at Foo (+995555123456)", "url": "/leads/5"})
    assert r.json() == {"ok": True}
    f = lines(caplog, "app.client")[-1].fields
    assert (f["user_id"], f["user"], f["kind"], f["url"]) == (u.id, "Нино", "react", "/leads/5")
    assert "555123" not in f["stack"]
    assert client.post("/api/client-log", content=b"x" * 20_000).status_code == 413
    for _ in range(30):
        client.post("/api/client-log", json={"message": "spam"})
    assert client.post("/api/client-log", json={"message": "spam"}).status_code == 429
