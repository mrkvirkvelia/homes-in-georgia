"""Test database for the bot: TEST_DATABASE_URL in its own schema (BOT_TEST_SCHEMA, default bot_test), so the backend's
tests on the same database don't collide. The schema comes from backend/alembic (upgrade head); while that is missing,
from test/schema_fallback.sql. A changed migration set rebuilds the schema. reset() empties every table."""
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import psycopg

import db

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC = ROOT / "backend" / "alembic"
FALLBACK = Path(__file__).with_name("schema_fallback.sql")
SCHEMA = os.environ.get("BOT_TEST_SCHEMA", "bot_test")
_ready = []


def _setup_env():
    """Before anything imports app.config: the backend engine and notify use the test schema; no real Telegram."""
    os.environ["DATABASE_URL"] = url(driver=True)
    os.environ.setdefault("BOT_TOKEN", "")
    db.URL = url()


def base_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url and (ROOT / ".env").exists():
        m = re.search(r"^TEST_DATABASE_URL=(.+)$", (ROOT / ".env").read_text(), re.M)
        url = m and m[1].strip()
    return url or "postgresql://postgres@/homes_test?host=/Users/mihailfedrunov/.hig-pg/data"


def url(driver=False):
    """TEST_DATABASE_URL with search_path = the test schema (driver=True keeps/sets SQLAlchemy's +psycopg)."""
    u = base_url()
    u = u + ("&" if "?" in u else "?") + "options=" + quote(f"-csearch_path={SCHEMA}")
    u = re.sub(r"^postgres(?:ql)?(\+\w+)?://", "postgresql+psycopg://" if driver else "postgresql://", u)
    return u


def _db_key(u):
    """(host, port, database) of a Postgres URL, driver and credentials aside (a socket dir in ?host= counts as host)."""
    p = urlsplit(re.sub(r"^postgres(?:ql)?(\+\w+)?://", "postgresql://", u.strip()))
    return (p.hostname or parse_qs(p.query).get("host", [""])[0], p.port or 5432, unquote(p.path.lstrip("/")))


def check_test_db(test_url, main_url, schema):
    """ensure() drops and rebuilds SCHEMA, reset() truncates it: only a test schema of a test database, never the
    app's own DATABASE_URL (a .env copied from prod, BOT_TEST_SCHEMA=public by mistake)."""
    name = _db_key(test_url)[2]
    if "test" not in name.lower():
        raise RuntimeError(f"TEST_DATABASE_URL points at database {name!r}: the bot tests drop a schema in it, so its name "
                           "must contain 'test' (e.g. homes_test)")
    if "test" not in schema.lower():
        raise RuntimeError(f"BOT_TEST_SCHEMA={schema!r}: the bot tests drop it, so its name must contain 'test' (default bot_test)")
    if main_url and _db_key(main_url) == _db_key(test_url):
        raise RuntimeError("TEST_DATABASE_URL is the same database as DATABASE_URL: the bot tests would write into it")


def _main_url():
    """The app's DATABASE_URL (environment, else the repo .env), read before _setup_env points it at the test schema."""
    u = os.environ.get("DATABASE_URL")
    if not u and (ROOT / ".env").exists():
        m = re.search(r"^DATABASE_URL=(.+)$", (ROOT / ".env").read_text(), re.M)
        u = m and m[1].strip()
    return u or None


def fingerprint():
    if (ALEMBIC / "versions").is_dir():
        files = sorted(p for p in (ALEMBIC / "versions").glob("*.py"))
        return "alembic:" + hashlib.md5(b"".join(p.read_bytes() for p in files)).hexdigest()
    return "fallback:" + hashlib.md5(FALLBACK.read_bytes()).hexdigest()


def ensure():
    if _ready:
        return
    check_test_db(base_url(), MAIN_URL, SCHEMA)
    fp = fingerprint()
    with psycopg.connect(db.dsn(base_url()), autocommit=True) as c:
        cur = c.execute("SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname = %s", (SCHEMA,)).fetchone()
        if cur and cur[0] == fp:
            _ready.append(fp)
            return
        c.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        c.execute(f'CREATE SCHEMA "{SCHEMA}"')
    if fp.startswith("alembic:"):
        env = {**os.environ, "DATABASE_URL": url(driver=True), "TEST_DATABASE_URL": url(driver=True)}
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("alembic upgrade head failed:\n" + r.stdout + r.stderr)
    else:
        with psycopg.connect(url()) as c:
            c.execute(FALLBACK.read_text())
    with psycopg.connect(db.dsn(base_url()), autocommit=True) as c:
        c.execute(f"COMMENT ON SCHEMA \"{SCHEMA}\" IS '{fp}'")
    _ready.append(fp)


def reset():
    """Empty test schema, db.URL pointed at it, bot seeds applied (db.init)."""
    ensure()
    db.URL = url()
    with psycopg.connect(url(), autocommit=True) as c:
        tables = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s AND tablename != 'alembic_version'",
                                          (SCHEMA,))]
        if tables:
            c.execute("TRUNCATE " + ", ".join(f'"{SCHEMA}"."{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
    db.init()


MAIN_URL = _main_url()
_setup_env()
