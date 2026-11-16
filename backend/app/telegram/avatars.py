"""Telegram profile photos for the team (Irakli 2026-11-11: «аватарки с тг подгрузим»): an active user without a stored
photo -> getUserProfilePhotos (the main bot), else the operator userbot by tg_id / @username (privacy can hide the photo
from bots, not from a contact) -> 256 px JPEG -> storage avatars/u<id>.jpg -> users.photo_url = /api/media/avatars/u<id>.jpg.
External links (t.me/i/userpic expires, Drive, junk) are never kept: no photo found -> NULL, the initials show.
A photo uploaded in the CRM (avatars/u<id>-<hex>.jpg, users.set_avatar) is never touched.

Run: cd backend && python -m app.telegram.avatars [--all]   (--all: refresh the ones already set by this script)"""
import base64
import io
import logging
import sys

import httpx
from sqlalchemy import select

from app import storage
from app.db import SessionLocal
from app.models import User
from app.telegram import client as tg
from app.telegram.client import conf

log = logging.getLogger(__name__)
PX = 256


def jpeg(raw: bytes) -> bytes | None:
    """Any image -> a PX JPEG, None if it is not one."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw))
    except Exception:  # noqa: BLE001 — an HTML page, an empty body
        return None
    with im:
        im = im.convert("RGB")
        im.thumbnail((PX, PX))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        return out.getvalue()


def from_bot(tg_id: int) -> bytes | None:
    res = tg.call("getUserProfilePhotos", user_id=tg_id, limit=1)
    sizes = ((res or {}).get("photos") or [[]])[0]
    if not sizes:
        return None
    f = tg.call("getFile", file_id=sizes[-1]["file_id"])
    if not f or not f.get("file_path"):
        return None
    api = conf("TG_API_BASE", "https://api.telegram.org").rstrip("/")
    r = httpx.get(f"{api}/file/bot{conf('BOT_TOKEN').strip()}/{f['file_path']}", timeout=30)
    return r.content if r.status_code == 200 else None


def from_userbot(tg_id: int | None, username: str | None) -> bytes | None:
    """The operator account's view (userbot POST /photo) — it sees photos hidden from bots."""
    url = conf("USERBOT_URL").strip().rstrip("/")
    if not url:
        return None
    try:
        r = httpx.post(f"{url}/photo", json={"tg_id": tg_id, "username": username},
                       headers={"X-Userbot-Token": conf("SECRET_KEY")}, timeout=40)
        b = r.json()
        return base64.b64decode(b["b64"]) if r.status_code == 200 and b.get("b64") else None
    except Exception as e:  # noqa: BLE001
        log.warning("userbot photo %s/%s failed: %r", tg_id, username, e)
        return None


def fetch(tg_id: int | None, username: str | None = None) -> bytes | None:
    """The user's current profile photo (raw image bytes), or None (no photo / hidden / Telegram down)."""
    return (from_bot(tg_id) if tg_id else None) or from_userbot(tg_id, (username or "").lstrip("@") or None)


def uploaded(u: User) -> bool:
    """A photo set by hand in the CRM (users.set_avatar: avatars/u<id>-<hex>.jpg)."""
    return (u.photo_url or "").startswith(f"/api/media/avatars/u{u.id}-")


def store_photo(u: User, raw: bytes | None) -> bool:
    """raw image -> avatars/u<id>.jpg + photo_url; False if it is not an image."""
    data = jpeg(raw) if raw else None
    if not data:
        return False
    key = f"avatars/u{u.id}.jpg"
    storage.put(key, data)
    u.photo_url = f"/api/media/{key}"
    return True


def save_from_url(u: User, url: str) -> bool:
    """Telegram sign-in: the photo_url it hands us (t.me/i/userpic, expires) -> our stored copy; else the bot's view.
    Never raises: a sign-in must not fail over a picture."""
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True)
        return store_photo(u, r.content if r.status_code == 200 else None) or bool(u.tg_id and store_photo(u, from_bot(u.tg_id)))
    except Exception as e:  # noqa: BLE001
        log.warning("avatar from %s failed: %r", url, e)
        return False


def run(refresh: bool = False, out=print) -> tuple[int, int]:
    """-> (set, without a photo)."""
    done = missing = 0
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.is_active.is_(True), User.deleted_at.is_(None),
                                              (User.tg_id.isnot(None)) | (User.username.isnot(None)))).all()
        for u in users:
            own = (u.photo_url or "").startswith("/api/media/avatars/")
            if uploaded(u) or (own and not refresh):
                continue
            if store_photo(u, fetch(u.tg_id, u.username)):
                done += 1
            else:
                missing += 1
                out(f"  no photo: u{u.id} {u.name} tg={u.tg_id} @{u.username}")
                if not own:
                    u.photo_url = None  # a dead external link -> the initials
            db.commit()
    out(f"avatars: {done} set, {missing} without a photo visible to the bot or the operator account")
    return done, missing


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run(refresh="--all" in sys.argv)
