"""Сверка с каналом (Stanislav 11-22, Irakli 11-20): operators still delete posts by hand in the channel, the Bot API
sends no event for that, so an object whose post is gone stayed on hge.ge (164 hidden by hand 11-20). Every few hours
each object on the site with a t.me post is checked on the public preview: «Post not found» → off the site (site_hidden),
an event on the object says why. No Telegram account needed."""
import logging
import re
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Property
from app.services.common import log_event

log = logging.getLogger(__name__)
POST = re.compile(r"t\.me/([A-Za-z]\w{3,})/(\d+)")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
MAX_SHARE = 0.5  # more than this share «gone» at once (and more than 10): t.me answers oddly, hide nothing


def gone(c: httpx.Client, channel: str, msg: int) -> bool | None:
    """True: the post was deleted; False: it is there; None: can't tell (network, an odd page)."""
    try:
        r = c.get(f"https://t.me/{channel}/{msg}", params={"embed": "1", "mode": "tme"})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    if "tgme_widget_message_error" in r.text:
        return True
    return False if "tgme_widget_message" in r.text else None


def run(db: Session, pause: float = 0.5, out=log.info) -> int:
    """Hide the objects whose channel post is gone -> how many were hidden."""
    rows = db.scalars(select(Property).where(Property.status == "published", ~Property.site_hidden,
                                             Property.post_url.is_not(None))).all()
    posts = [(p, m) for p in rows if (m := POST.search(p.post_url or ""))]
    dead = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as c:
        for p, m in posts:
            if gone(c, m[1], int(m[2])):
                dead.append(p)
            time.sleep(pause)
    if len(dead) > 10 and len(dead) > MAX_SHARE * len(posts):
        out(f"post sync: {len(dead)} of {len(posts)} posts look deleted, hiding nothing (t.me answers oddly?)")
        return 0
    for p in dead:
        p.site_hidden = True
        log_event(db, "property", p.id, "site_off", None, label="сверка с каналом", reason="пост удалён в канале",
                  post_url=p.post_url)
    db.commit()
    if dead:
        from app.services import site_feed
        site_feed.clear_cache()
    out(f"post sync: {len(posts)} posts checked, {len(dead)} deleted -> off the site: {[p.id for p in dead]}")
    return len(dead)
