"""The signing machinery shared by the NDA (services/nda.py) and «Документ на подпись» (services/sign_docs.py): the
signer's Telegram confirmation — the Login Widget's answer (HMAC with the bot token) or /start <prefix>_<token> in the
CRM sign-in bot (telegram/login_bot.py) — written into any signer row with the tg_* columns (tg_id, tg_username,
tg_name, tg_auth_date, tg_hash)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings as env
from app.services.common import now
from app.services.errors import DomainError

CONFIRM_TTL = timedelta(hours=1)  # the Telegram confirmation is good for this long before signing


def test_mode() -> bool:
    """A test stand (settings.TEST_MODE, when it has one): Telegram is off there, the page offers a marked stand-in."""
    return bool(getattr(env, "TEST_MODE", False))


def confirmed(row) -> bool:
    return bool(row.tg_id and row.tg_auth_date and now() - row.tg_auth_date < CONFIRM_TTL)


def widget(data: dict, username: str | None, test: bool | None = None) -> dict:
    """The Login Widget's answer → checked fields; on a test stand {test: true} → a marked stand-in."""
    if (test_mode() if test is None else test) and data.get("test") is True:
        return {"id": "0", "username": username or "test", "first_name": "TEST", "auth_date": str(int(now().timestamp())),
                "hash": "test-mode-" + secrets.token_hex(8)}
    from app.api.auth import verify_login_widget
    payload = {k: (str(v) if v is not None else None) for k, v in data.items() if k in
               ("id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash")}
    fields = verify_login_widget(payload, env.LOGIN_BOT_TOKEN or env.BOT_TOKEN, max_age=int(CONFIRM_TTL.total_seconds()))
    fields["hash"] = payload["hash"]
    return fields


def from_bot(token: str, frm: dict) -> dict:
    """A private /start message's sender → the fields; the confirmation code is an HMAC (bot token) of the link's token,
    the account and the time."""
    at = int(now().timestamp())
    key = hashlib.sha256((env.LOGIN_BOT_TOKEN or env.BOT_TOKEN or "").encode()).digest()
    code = "bot-" + hmac.new(key, f"{token}:{frm['id']}:{at}".encode(), hashlib.sha256).hexdigest()
    return {**{k: frm.get(k) for k in ("id", "username", "first_name", "last_name")}, "auth_date": str(at), "hash": code}


def apply(row, fields: dict, *, telegram: str | None = None, tg_id=None, wrong: str = "") -> None:
    """The fields → the row. Only the named @username (telegram) / the team member's account (tg_id) passes."""
    got = (fields.get("username") or "").lower()
    if telegram and got != telegram.lower() or tg_id and str(fields.get("id")) != str(tg_id) and fields.get("id") != "0":
        raise DomainError("wrong_telegram", wrong or f"Это документ для Telegram @{telegram or '…'}. Войдите этим аккаунтом", 403)
    row.tg_id, row.tg_username = str(fields.get("id")), fields.get("username") or None
    row.tg_name = " ".join(x for x in (fields.get("first_name"), fields.get("last_name")) if x) or None
    row.tg_auth_date = datetime.fromtimestamp(int(fields.get("auth_date") or 0), timezone.utc)
    row.tg_hash = fields.get("hash")
