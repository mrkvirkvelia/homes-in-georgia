"""hge.ge's own visitor counter: the site posts anonymous events (web/src/lib/analytics.ts) to /api/public/site/events,
they land in `site_events`, and «Аналитика» (superadmins only) reads the report built here.

The report is the same as the Google Apps Script it replaces (apps-script/site-analytics.gs aggregate_ in
PlatformDGE/-rentintbilisi-crm), so the CRM page did not change.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SiteEvent

PERIODS = (1, 7, 30, 90)
TYPES = {"pageview", "listing", "contact", "share", "fav", "search", "error", "perf", "social"}
MAX_BATCH = 50
CACHE_SEC = 120

_cache: dict[int, tuple[float, dict]] = {}
_lock = threading.Lock()


def _s(v, n: int = 120) -> str:
    return ("" if v is None else str(v))[:n]


def clean(events) -> list[dict]:
    """Only known event types and short values get in: the endpoint is public."""
    out = []
    for x in (events if isinstance(events, list) else [])[:MAX_BATCH]:
        if not isinstance(x, dict) or x.get("t") not in TYPES:
            continue
        data = x.get("x") if isinstance(x.get("x"), dict) else {}
        if len(json.dumps(data, ensure_ascii=False)) > 600:
            data = {}
        out.append(dict(type=x["t"], visitor=_s(x.get("v"), 40), session=_s(x.get("s"), 40), path=_s(x.get("p"), 200),
                        listing=_s(x.get("l"), 40), service=_s(x.get("sv"), 30), agent=_s(x.get("ag"), 60),
                        source=_s(x.get("src"), 40), medium=_s(x.get("med"), 40), campaign=_s(x.get("cmp"), 80),
                        lang=_s(x.get("lang"), 5), theme=_s(x.get("th"), 6), device=_s(x.get("dev"), 8),
                        new=bool(x.get("nw")), data=data))
    return out


def record(db: Session, events) -> int:
    rows = clean(events)
    if rows:
        db.add_all(SiteEvent(**r) for r in rows)
        db.commit()
    return len(rows)


def _pct(a, b):
    return round(a / b * 1000) / 10 if b else 0


def _q(arr, p):
    if not arr:
        return 0
    s = sorted(arr)
    return round(s[min(len(s) - 1, int(p * len(s)))])


def _inc(o, k, n=1):
    k = "—" if k in ("", None) else str(k)
    o[k] = o.get(k, 0) + n


def _top(o, n=20):
    return sorted(({"name": k, "n": v} for k, v in o.items()), key=lambda x: -x["n"])[:n]


def search_key(service, q) -> str:
    """"rent · beds=2 · district=Vake": the same search reads the same in the report."""
    parts = sorted(x for x in str(q or "").split("&") if x and not x.startswith("sort="))
    return " · ".join([service or "—", *(unquote_plus(x) for x in parts)])


def _totals(evs):
    v, nv, s, cs = set(), set(), set(), set()
    pv = lv = c = sh = fv = 0
    for e in evs:
        v.add(e.visitor), s.add(e.session)
        if e.new:
            nv.add(e.visitor)
        t = e.type
        pv += t == "pageview"
        lv += t == "listing"
        if t == "contact":
            c += 1
            cs.add(e.session)
        sh += t == "share"
        fv += t == "fav" and bool((e.data or {}).get("on"))
    return {"visitors": len(v), "newVisitors": len(nv), "sessions": len(s), "pageviews": pv, "listingViews": lv,
            "contacts": c, "contactSessions": len(cs), "conversion": _pct(len(cs), len(s)), "shares": sh, "favs": fv}


def aggregate(cur: list, prev: list, start: datetime, end: datetime, days: int) -> dict:
    tz = ZoneInfo(settings.TZ)
    day = lambda t: t.astimezone(tz).strftime("%Y-%m-%d")  # noqa: E731
    daily = {}
    d = start
    while d <= end + timedelta(milliseconds=1):
        daily.setdefault(day(d), {"visitors": set(), "sessions": set(), "contacts": 0, "views": 0})
        d += timedelta(days=1)
    for e in cur:
        x = daily.setdefault(day(e.at), {"visitors": set(), "sessions": set(), "contacts": 0, "views": 0})
        x["visitors"].add(e.visitor), x["sessions"].add(e.session)
        x["contacts"] += e.type == "contact"
        x["views"] += e.type == "listing"
    daily_list = [{"d": k, "visitors": len(x["visitors"]), "sessions": len(x["sessions"]), "contacts": x["contacts"], "views": x["views"]}
                  for k, x in sorted(daily.items())]

    # Sessions by source and campaign; a session counts once, with its first source.
    sess = {}
    for e in cur:
        x = sess.setdefault(e.session, {"src": e.source or "direct", "med": e.medium, "cmp": e.campaign, "contact": False})
        x["contact"] |= e.type == "contact"
    src, cmp = {}, {}
    for x in sess.values():
        a = src.setdefault(x["src"], {"name": x["src"], "sessions": 0, "contacts": 0})
        a["sessions"] += 1
        a["contacts"] += x["contact"]
        if x["cmp"] or x["med"]:
            b = cmp.setdefault(f'{x["src"]} · {x["cmp"] or x["med"]}', {"name": x["cmp"] or x["med"], "source": x["src"], "sessions": 0, "contacts": 0})
            b["sessions"] += 1
            b["contacts"] += x["contact"]

    def with_conv(o):
        for x in o.values():
            x["conversion"] = _pct(x["contacts"], x["sessions"])
        return sorted(o.values(), key=lambda x: -x["sessions"])

    L = {}

    def listing(e):
        if not e.listing:
            return None
        return L.setdefault(e.listing, {"id": e.listing, "service": e.service or "", "agent": e.agent or "", "views": 0,
                                        "viewers": set(), "contacts": 0, "shares": 0, "favs": 0})

    contacts_by, shares_by, social_by, devices, langs, themes = {}, {}, {}, {}, {}, {}
    searches, zero, errors, loads, lcps, loads_by, dev_seen = {}, {}, {}, [], [], {}, set()
    for e in cur:
        t, x = e.type, e.data or {}
        if e.session not in dev_seen:
            dev_seen.add(e.session)
            _inc(devices, e.device), _inc(langs, e.lang), _inc(themes, e.theme)
        if t == "listing" and (l := listing(e)):
            l["views"] += 1
            l["viewers"].add(e.visitor)
        if t == "contact":
            _inc(contacts_by, x.get("ch"))
            if l := listing(e):
                l["contacts"] += 1
        if t == "social":
            _inc(social_by, x.get("ch"))
        if t == "share":
            _inc(shares_by, x.get("ch"))
            if l := listing(e):
                l["shares"] += 1
        if t == "fav" and x.get("on") and (l := listing(e)):
            l["favs"] += 1
        if t == "search":
            k = search_key(e.service, x.get("q"))
            _inc(searches, k)
            if str(x.get("n")) == "0":
                _inc(zero, k)
        if t == "error":
            m = str(x.get("msg") or "")[:140]
            er = errors.setdefault(m, {"name": m, "n": 0, "sessions": set(), "page": e.path, "device": e.device, "last": 0})
            er["n"] += 1
            er["sessions"].add(e.session)
            er["last"] = max(er["last"], int(e.at.timestamp() * 1000))
        if t == "perf":
            load, lcp = x.get("load"), x.get("lcp")
            if isinstance(load, (int, float)) and 0 < load < 120000:
                loads.append(load)
                loads_by.setdefault(e.device or "—", []).append(load)
            if isinstance(lcp, (int, float)) and 0 < lcp < 120000:
                lcps.append(lcp)

    listings = list(L.values())
    for x in listings:
        x["viewers"] = len(x["viewers"])
        x["conversion"] = _pct(x["contacts"], x["viewers"])
    agents = {}
    for x in listings:
        a = agents.setdefault(x["agent"] or "—", {"name": x["agent"] or "—", "listings": 0, "views": 0, "contacts": 0})
        a["listings"] += 1
        a["views"] += x["views"]
        a["contacts"] += x["contacts"]
    for a in agents.values():
        a["conversion"] = _pct(a["contacts"], a["views"])
    for er in errors.values():
        er["sessions"] = len(er["sessions"])

    return {
        "period": {"from": int(start.timestamp() * 1000), "to": int(end.timestamp() * 1000), "days": days},
        "totals": _totals(cur), "prev": _totals(prev), "daily": daily_list,
        "contactsBy": contacts_by, "sources": with_conv(src), "campaigns": with_conv(cmp)[:30],
        "listings": sorted(listings, key=lambda x: (-x["views"], -x["contacts"]))[:40],
        "bestListings": sorted((x for x in listings if x["contacts"] > 0), key=lambda x: (-x["contacts"], -x["conversion"]))[:15],
        "noResponse": sorted((x for x in listings if x["contacts"] == 0 and x["viewers"] >= 5), key=lambda x: -x["viewers"])[:30],
        "agents": sorted(agents.values(), key=lambda a: (-a["contacts"], -a["views"])),
        "searches": _top(searches, 25), "zeroSearches": _top(zero, 25),
        "sharesBy": shares_by, "socialBy": social_by, "devices": devices, "langs": langs, "themes": themes,
        "errors": sorted(errors.values(), key=lambda x: -x["n"])[:20],
        "perf": {"loadMedian": _q(loads, .5), "loadP75": _q(loads, .75), "lcpMedian": _q(lcps, .5), "lcpP75": _q(lcps, .75),
                 "n": len(loads), "byDevice": {k: {"median": _q(v, .5), "p75": _q(v, .75), "n": len(v)} for k, v in loads_by.items()}},
    }


def report(db: Session, days: int = 7, fresh: bool = False) -> dict:
    if days not in PERIODS:
        days = 7
    with _lock:
        hit = _cache.get(days)
        if hit and not fresh and time.monotonic() - hit[0] < CACHE_SEC:
            return hit[1]
    # ponytail: the period is aggregated in Python (fine for tens of thousands of events); move to SQL GROUP BY if it grows to millions
    end = datetime.now(timezone.utc)
    start, prev_start = end - timedelta(days=days), end - timedelta(days=2 * days)
    rows = db.execute(select(SiteEvent).where(SiteEvent.at >= prev_start, SiteEvent.at <= end)).scalars().all()
    out = aggregate([e for e in rows if e.at >= start], [e for e in rows if e.at < start], start, end, days)
    with _lock:
        _cache[days] = (time.monotonic(), out)
    return out


def clear_cache():
    with _lock:
        _cache.clear()
