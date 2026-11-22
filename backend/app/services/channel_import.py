"""Посты канала → объекты CRM (Stanislav 11-22: «объекты, которые они выкладывают в канал, пусть сами добавляются в
CRM, раз они ей пока не пользуются»). Operators post flats straight to the agency channel (193 posts in two weeks, 4
through the CRM), so hge.ge showed 81 rentals against 250 in the channel. Every half hour the channel is read through the
Telegram account (the reader, else the operator's userbot: rich posts and photos the web preview hides) and each new
flat post becomes a published object on the site: the card fields and generator tags from the text (the old base's
parsers), the agent by the post's hashtag (#Roman2), the photos, a map point. A post of a flat the CRM already has (a
repost: the same address and bedrooms) moves that object's link to the new post instead. Deleted posts: post_sync.py."""
import base64
import logging
import re
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings as env
from app.importers import legacy_objects as L
from app.models import Event, Property, PropertyMedia, PropertyPublication, User
from app.services.common import log_event, now

log = logging.getLogger(__name__)
CHANNEL = "rent_tbilisi_ge"  # ponytail: the rent channel only (David's 81 vs 250); sale_in_tbilisi etc. when asked
BACKFILL_DAYS = 14
PAGE = 150                   # messages per request: ~15 albums with their photos inside the reader's 240 s
LIVE = ("published", "taken", "owner_confirmed", "shoot_scheduled", "media_uploaded", "review", "returned")


def _readers() -> list[str]:
    from app.api.content import reader_url
    return [u for u in (reader_url(), (env.USERBOT_URL or "").strip().rstrip("/")) if u]


def ask(path: str, body: dict, timeout: float = 250) -> dict | None:
    """POST to the reader account, else the operator's userbot -> the reply, None when neither answers."""
    for url in _readers():
        try:
            r = httpx.post(f"{url}{path}", json=body, headers={"X-Userbot-Token": env.SECRET_KEY}, timeout=timeout)
            if r.status_code == 200 and r.json().get("ok"):
                return r.json()
        except (httpx.HTTPError, ValueError):
            pass
    return None


def posts(channel: str, min_id: int) -> list[dict] | None:
    """The channel's posts after min_id (none yet: the last BACKFILL_DAYS), oldest first; None: no account answered."""
    out, max_id, since = [], 0, (now() - timedelta(days=BACKFILL_DAYS)).isoformat()
    while True:
        r = ask("/channel", {"user": channel, "min_id": min_id, "max_id": max_id, "limit": PAGE, "photos": 10})
        if r is None:
            return None if not out else sorted(out, key=lambda p: p["id"])
        got = r["posts"]
        out += [p for p in got if min_id or p["date"] >= since]
        if not got or (not min_id and min(p["date"] for p in got) < since) or len(out) > 400:
            break
        max_id = min(p["id"] for p in got)
    return sorted(out, key=lambda p: p["id"])


def cursor(db: Session, channel: str) -> int:
    ev = db.scalar(select(Event).where(Event.entity == "channel", Event.entity_id == channel, Event.action == "channel_import")
                   .order_by(Event.id.desc()).limit(1))
    return int((ev.data or {}).get("max_id") or 0) if ev else 0


def known(db: Session, channel: str, msg: int) -> bool:
    """The CRM posted it (or imported it before)."""
    url = f"https://t.me/{channel}/{msg}"
    if db.scalar(select(Property.id).where(Property.post_url == url).limit(1)):
        return True
    return bool(db.scalar(select(PropertyPublication.id).where(
        (PropertyPublication.url == url) | PropertyPublication.messages["ids"].contains([msg])).limit(1)))


def same_flat(db: Session, address: str | None, bedrooms: int | None) -> Property | None:
    """A CRM object of this flat: the same street + house, the same bedrooms (a channel repost of an object)."""
    key = L.addr_key(address)
    if not key:
        return None
    street = key.split("|")[0].split()[0]
    gone_post = (Property.status == "archived") & (Property.source_type == "channel") & (Property.archive_reason == "not_actual")
    rows = db.scalars(select(Property).where(Property.status.in_(LIVE) | gone_post, Property.bedrooms == bedrooms,
                                             Property.address.ilike(f"%{street}%")).order_by(Property.id.desc()))
    return next((p for p in rows if L.addr_key(p.address) == key), None)


def _agent(db: Session, text: str) -> int | None:
    tags = [t.lower() for t in L.tags_of(text)]
    users = db.scalars(select(User).where(func.lower(User.agent_tag).in_(tags))).all() if tags else []
    return users[0].id if users else None


def _point(p: Property) -> None:
    from app.services import geo
    try:
        hit = (geo.search(f"{p.address}, Tbilisi").get("items") or [None])[0]
    except Exception:  # noqa: BLE001 — no map point is no reason to lose the object
        hit = None
    if hit:
        p.lat, p.lng = hit["lat"], hit["lng"]
        p.district = p.district or hit.get("district")


def _photos(db: Session, p: Property, photos: list[dict]) -> None:
    from app import storage
    from app.services.matching import photo_hash
    for n, ph in enumerate(photos):
        data = base64.b64decode(ph["b64"])
        key = f"properties/{p.id}/tg{ph['id']}.jpg"
        storage.put(key, data)
        storage.put_preview(key, data)
        db.add(PropertyMedia(property_id=p.id, kind="photo", path=key, position=n, dhash=photo_hash(data)))


def _relink(db: Session, p: Property, url: str, msg: int, channel: str) -> None:
    from app.services import properties as P
    old = p.post_url
    p.post_url, p.post_message_id, p.published_at = url, str(msg), now()
    if p.status == "archived":  # same_flat: only a channel object archived by post_sync
        p.status, p.archive_reason, p.archive_comment, p.archived_at = "published", None, None, None
    if p.status == "published":
        p.site_hidden = False
    P.record_publication(db, p, "tg", url, str(msg))
    log_event(db, "property", p.id, "channel_repost", None, label="пост в канале", post_url=url, old_post_url=old)


def import_post(db: Session, channel: str, post: dict) -> str:
    """-> what happened: known / not_object / relinked / skipped (a live CRM object of the flat) / created."""
    from app.services import properties as P
    msg, text = int(post["id"]), post.get("text") or ""
    url = f"https://t.me/{channel}/{msg}"
    if known(db, channel, msg):
        return "known"
    if not L.is_object_text(text) or not post.get("photos"):
        return "not_object"
    fields = {f: parse(text) for f, parse in L.CARD_PARSERS.items()}
    if p := same_flat(db, fields["address"], fields["bedrooms"]):
        if p.status not in ("published", "archived"):
            return "skipped"  # the agent is working on it in the CRM: his card, his post
        _relink(db, p, url, msg, channel)
        db.commit()
        return "relinked"
    t = now()
    p = Property(source_type="channel", source_url=url, source_external_id=f"tg:{channel}/{msg}", status="published",
                 post_url=url, post_message_id=str(msg), published_at=t, verified_at=t, site_hidden=False,
                 description=text, post_fields=L.post_fields_of(text) or None, agent_id=_agent(db, text),
                 currency="USD", **{k: v for k, v in fields.items() if v not in (None, "")})
    if fields.get("district"):
        from app import districts
        p.district = districts.label(fields["district"]) or fields["district"]
    _point(p)
    db.add(p)
    db.flush()
    _photos(db, p, post["photos"])
    P.record_publication(db, p, "tg", url, str(msg))
    log_event(db, "property", p.id, "imported_from_channel", None, label="пост в канале", post_url=url)
    db.commit()
    return "created"


def run(db: Session, channel: str = CHANNEL) -> dict:
    start = cursor(db, channel)
    got = posts(channel, start)
    if got is None:
        log.warning("channel import %s: no Telegram account answered", channel)
        return {}
    counts: dict = {}
    for post in got:
        try:
            r = import_post(db, channel, post)
        except Exception:  # noqa: BLE001 — one odd post must not stop the rest
            db.rollback()
            log.exception("channel import %s/%s failed", channel, post.get("id"))
            r = "failed"
        counts[r] = counts.get(r, 0) + 1
    if got:
        log_event(db, "channel", channel, "channel_import", None, max_id=max(p["id"] for p in got), **counts)
        db.commit()
        from app.services import catalog, site_feed
        site_feed.clear_cache()
        catalog.sync_all(db)
        db.commit()
    log.info("channel import %s after %s: %s", channel, start, counts)
    return counts
