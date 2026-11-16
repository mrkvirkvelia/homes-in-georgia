"""Integration keys entered in the CRM (Управление → Ключи, admin and above): rows `key:<NAME>` of the settings table, over
.env. Every process (api, worker, bot, the parser's scripts) calls refresh(): at most once a minute it puts them into
os.environ and onto app.config.settings, so a new Apify / OpenAI / MapTiler key works without a restart; a key removed
in the CRM falls back to .env. The values never leave the server: the API shows the last 4 characters only."""
import os
import re
import time

from app.config import settings as env

PREFIX = "key:"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
# infrastructure, logins and the bot's own tokens: .env only (a typo here would take the CRM down)
BLOCKED = {"DATABASE_URL", "TEST_DATABASE_URL", "SECRET_KEY", "BOT_TOKEN", "LOGIN_BOT_TOKEN", "API_ID", "API_HASH",
           "OPERATOR_USERBOT_SESSION", "ADMIN_BOOTSTRAP_LOGIN", "ADMIN_BOOTSTRAP_PASSWORD", "SUPERADMIN_TG_IDS",
           "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_BUCKET", "MEDIA_STORAGE", "MEDIA_DIR", "POSTGRES_PASSWORD",
           "GOOGLE_SA_JSON", "APP_ENV", "DEV_CORS", "PASSWORD_LOGIN", "PUBLIC_URL", "CHROME_BIN", "LLM_PROVIDER"}
KNOWN = {  # NAME -> (what it is, in plain words; where it is used). Shown even when empty; any other NAME can be added
    "OPENAI_API_KEY": ("Нейросеть: ключ OpenAI / ProxyAPI", "Все вызовы ИИ идут через этот ключ"),
    "OPENAI_BASE_URL": ("Нейросеть: адрес API", "Например https://api.proxyapi.ru/openai/v1"),
    "LLM_MODEL": ("Нейросеть: модель", "Например gpt-4.1-mini"),
    "APIFY_TOKENS": ("Apify: ключи для парсера Facebook", "Можно несколько через запятую, берутся по очереди"),
    "APIFY_TOKEN": ("Apify: один ключ", "Если список выше пустой"),
    "MAPTILER_KEY": ("Карты MapTiler", "Подложка карт в CRM и на сайте"),
}
TTL = 60
_ORIG = {k: os.environ.get(k) for k in KNOWN}  # .env / container values, for keys removed in the CRM
_applied: set[str] = set()
_at = 0.0


def valid(name: str) -> bool:
    return bool(NAME_RE.match(name)) and name not in BLOCKED


def _set(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    if name in type(env).model_fields:
        setattr(env, name, value if value is not None else type(env).model_fields[name].default)


def apply(rows: dict[str, str]) -> None:
    """rows: NAME -> value from the CRM. Sets them; the ones no longer there go back to .env."""
    global _at
    for name in _applied - rows.keys():
        _set(name, _ORIG.get(name))
    for name, value in rows.items():
        if not valid(name):
            continue
        if name not in _applied:
            _ORIG.setdefault(name, os.environ.get(name))
        _set(name, value)
    _applied.clear()
    _applied.update(n for n in rows if valid(n))
    _at = time.monotonic()


def read(db) -> dict[str, str]:
    from app.models import Setting
    return {r.key[len(PREFIX):]: r.value for r in db.query(Setting).filter(Setting.key.startswith(PREFIX)) if r.value}


def refresh(force: bool = False) -> None:
    """Re-read the CRM keys if the last read is older than TTL. Never raises: a DB hiccup keeps the current keys."""
    if not force and time.monotonic() - _at < TTL and _at:
        return
    try:
        from app.db import SessionLocal
        with SessionLocal() as db:
            apply(read(db))
    except Exception:  # noqa: BLE001
        pass
