"""Дубли в канале (David 11-20, Stanislav 11-22): right after an object is posted to the channel, the objects already
posted are searched for the same flat (similar.find, level «дубль» ≥ 85 %); each such pair goes to the operator in the
bot with «🗑 Удалить новый пост» / «Не дубль». Deleting = «В архив → Дубль» of the newer object into the older one
(its post leaves the channel, leads and files move over); «Не дубль» = the pair's decision, never asked again."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Property, SimilarDecision, User
from app.services import similar
from app.services.common import log_event

log = logging.getLogger(__name__)
ASKED = "channel_dup"  # Event(entity=ASKED, entity_id="<keep>:<drop>"): the operator was asked about this pair


def _posted(p: Property | None) -> bool:
    return p is not None and p.status == "published" and bool(p.post_url)


def pairs_for(db: Session, pid: int) -> list[dict]:
    """The posted objects that are the same flat as the freshly posted #pid -> [{keep, drop, pct, why}], the newer
    object always the one to drop; pairs already decided or asked about are left out."""
    p = db.get(Property, pid)
    if not _posted(p):
        return []
    out = []
    for c in similar.find(db, f"p:{pid}", None, include_ads=False):
        if c.get("level") != "same" or not c.get("property_id"):
            continue
        o = db.get(Property, c["property_id"])
        if not _posted(o):
            continue
        keep, drop = sorted((o.id, p.id))
        a, b = similar._pair(f"p:{keep}", f"p:{drop}")
        if db.scalar(select(SimilarDecision.id).where(SimilarDecision.a == a, SimilarDecision.b == b)) is not None:
            continue
        if db.scalar(select(Event.id).where(Event.entity == ASKED, Event.entity_id == f"{keep}:{drop}")) is not None:
            continue
        out.append({"keep": keep, "drop": drop, "pct": c.get("pct"), "why": c.get("why") or ", ".join(c.get("reasons") or [])})
    return out


def check(db: Session, pid: int) -> int:
    """Job channel_dups: ask the operator about each new pair -> how many were sent."""
    import httpx

    from app.services import post_sync
    from app.telegram import notify
    n = 0
    for x in pairs_for(db, pid):
        keep, drop = db.get(Property, x["keep"]), db.get(Property, x["drop"])
        # a post deleted by hand in the channel is no duplicate there any more (11-22: 10 of the 12 pairs found)
        with httpx.Client(headers={"User-Agent": post_sync.UA}, timeout=20, follow_redirects=True) as c:
            if any(post_sync.gone(c, m[1], int(m[2])) for p in (keep, drop) if (m := post_sync.POST.search(p.post_url))):
                continue
        notify.channel_duplicate(keep, drop, x["pct"], x["why"])
        log_event(db, ASKED, f"{keep.id}:{drop.id}", "asked", None, label="дубли в канале", pct=x["pct"])
        db.commit()
        n += 1
    return n


def resolve(db: Session, keep: int, drop: int, delete: bool, actor: User) -> str:
    """The operator's button -> what happened: deleted | kept | gone (one of them already left the channel)."""
    from app.services import properties as P
    k, d = db.get(Property, keep), db.get(Property, drop)
    if not (_posted(k) and _posted(d)):
        return "gone"
    if not delete:
        similar.decide(db, f"p:{keep}", f"p:{drop}", False, actor)
        db.commit()
        return "kept"
    P.archive(db, drop, actor, reason="duplicate", comment="дубль в канале (бот)", duplicate_of=keep)
    return "deleted"
