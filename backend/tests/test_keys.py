"""Управление → Ключи (app/keys.py): superadmin adds integration keys in the CRM; they win over .env in every process,
the value never comes back from the API, removing one falls back to .env, system keys stay .env-only."""
import os

from app import keys
from app.config import settings as env
from tests.conftest import auth, make_user


def test_keys_from_the_crm(db, client, monkeypatch):
    monkeypatch.setitem(keys._ORIG, "MAPTILER_KEY", "envmaptiler")
    monkeypatch.setattr(env, "MAPTILER_KEY", "envmaptiler")
    monkeypatch.setenv("MAPTILER_KEY", "envmaptiler")
    boss = make_user(db, "superadmin", "Давид")
    admin = make_user(db, "admin", "Иракли")
    h = auth(boss)

    assert client.get("/api/keys", headers=auth(admin)).status_code == 403
    assert client.put("/api/keys/APIFY_TOKEN", json={"value": "x" * 20}, headers=auth(admin)).status_code == 403

    secret = "crm-maptiler-key-12345678"
    r = client.put("/api/keys/maptiler_key", json={"value": secret}, headers=h)
    assert r.status_code == 200, r.text
    assert secret not in r.text
    row = next(k for k in r.json()["items"] if k["name"] == "MAPTILER_KEY")
    assert row["source"] == "crm" and row["tail"] == "5678"
    assert env.MAPTILER_KEY == secret and os.environ["MAPTILER_KEY"] == secret
    assert client.get("/api/config").json()["maptiler_key"] == secret
    # the general settings never show it
    assert not any(k.startswith("key:") for k in client.get("/api/settings", headers=h).json())

    # a new key by name (a future integration), shown without its value
    r = client.put("/api/keys/THREADS_TOKEN", json={"value": "threads-secret-abcdefgh"}, headers=h)
    assert "threads-secret" not in r.text and os.environ["THREADS_TOKEN"] == "threads-secret-abcdefgh"

    # system keys and bad names: .env only
    for name in ("SECRET_KEY", "DATABASE_URL", "BOT_TOKEN", "bad name"):
        assert client.put(f"/api/keys/{name}", json={"value": "zzzzzzzzzzzz"}, headers=h).status_code == 400

    # removed: back to .env
    r = client.delete("/api/keys/MAPTILER_KEY", headers=h)
    row = next(k for k in r.json()["items"] if k["name"] == "MAPTILER_KEY")
    assert row["source"] == "env" and env.MAPTILER_KEY == "envmaptiler"
    client.delete("/api/keys/THREADS_TOKEN", headers=h)
    assert "THREADS_TOKEN" not in os.environ
