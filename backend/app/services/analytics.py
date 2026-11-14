"""Dashboard metrics (apps-script getRentalStats / updateAnalyticsCache, now straight from Postgres)."""
import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.models import (FIELD_SQL, STAFF, ChannelPost, Client, Deal, Event, Lead, Listing, Property, PropertyListing, User,
                        at_least)
from app import districts
from app.services.common import TZ, now
from app.services.reports import month_bounds

LIVE = ("confirmed", "pending")


def _f(v) -> float:
    return float(v or 0)


def deals_summary(db: Session, month: str | None = None) -> dict:
    stmt = select(Deal).where(Deal.status.in_(LIVE))
    if month:
        stmt = stmt.where(Deal.month == month)
    rows = list(db.scalars(stmt))
    total = len(rows)
    comm = sum(_f(d.commission_total) for d in rows)
    plat = sum(_f(d.platform_amount) for d in rows)
    return {"total": total, "confirmed": sum(d.status == "confirmed" for d in rows),
            "exclusive": sum(bool(d.is_exclusive) for d in rows), "commission": round(comm), "platform": round(plat),
            "agents": round(sum(_f(d.agent_amount) for d in rows)), "price": round(sum(_f(d.price) for d in rows)),
            "avg_commission": round(comm / total) if total else 0}


def monthly(db: Session, months: int = 12) -> list[dict]:
    rows = db.execute(select(Deal.month, func.count(), func.sum(Deal.commission_total), func.sum(Deal.platform_amount),
                             func.sum(Deal.price)).where(Deal.status.in_(LIVE), Deal.month.isnot(None))
                      .group_by(Deal.month)).all()

    def key(m):
        try:
            mm, yy = m.split("/")
            return int(yy) * 12 + int(mm)
        except ValueError:
            return 0
    rows = sorted(rows, key=lambda r: key(r[0]))[-months:]
    return [{"month": m, "deals": n, "commission": round(_f(c)), "platform": round(_f(p)), "price": round(_f(pr))}
            for m, n, c, p, pr in rows]


def leaderboard(db: Session, month: str | None = None, limit: int = 15) -> list[dict]:
    stmt = (select(User.id, User.name, User.role, User.level, User.exclusive_deals, func.count(Deal.id),
                   func.coalesce(func.sum(Deal.agent_amount), 0), func.coalesce(func.sum(Deal.platform_amount), 0))
            .join(Deal, Deal.agent_id == User.id).where(Deal.status.in_(LIVE)))
    if month:
        stmt = stmt.where(Deal.month == month)
    rows = db.execute(stmt.group_by(User.id).order_by(func.count(Deal.id).desc()).limit(limit)).all()
    return [{"id": i, "name": n, "role": r, "level": lv, "exclusive_deals": ex, "deals": c, "agent_amount": round(_f(a)),
             "platform_amount": round(_f(p))} for i, n, r, lv, ex, c, a, p in rows]


def _avg_minutes(db: Session, start: str, end: str, since: datetime, group_by_actor: bool = False):
    """Average minutes between two lead events (e.g. created → operator_taken), optionally per actor of `end`."""
    a = select(Event.entity_id, func.min(Event.at).label("t")).where(Event.entity == "lead", Event.action == start,
                                                                   Event.at >= since).group_by(Event.entity_id).subquery()
    b = select(Event.entity_id, Event.actor_id, func.min(Event.at).label("t")).where(
        Event.entity == "lead", Event.action == end).group_by(Event.entity_id, Event.actor_id).subquery()
    diff = func.avg(func.extract("epoch", b.c.t - a.c.t) / 60)
    if group_by_actor:
        rows = db.execute(select(b.c.actor_id, diff, func.count()).join(a, a.c.entity_id == b.c.entity_id)
                          .group_by(b.c.actor_id)).all()
        return {aid: {"avg_min": round(float(m or 0), 1), "n": n} for aid, m, n in rows}
    m = db.scalar(select(diff).join(a, a.c.entity_id == b.c.entity_id))
    return round(float(m), 1) if m is not None else None


def response_times(db: Session, days: int = 30) -> dict:
    since = now() - timedelta(days=days)
    names = dict(db.execute(select(User.id, User.name)).all())
    per_op = _avg_minutes(db, "created", "operator_taken", since, True)
    per_agent = _avg_minutes(db, "agent_assigned", "slots_sent", since, True)
    return {"operator_take_avg_min": _avg_minutes(db, "created", "operator_taken", since),
            "agent_slots_avg_min": _avg_minutes(db, "agent_assigned", "slots_sent", since),
            "operators": [{"id": k, "name": names.get(k), **v} for k, v in per_op.items() if k],
            "agents": [{"id": k, "name": names.get(k), **v} for k, v in per_agent.items() if k]}


def funnel(db: Session, date_from: date | None = None, date_to: date | None = None) -> dict:
    lq = select(Lead.status, func.count()).group_by(Lead.status)
    pq = select(Property.status, func.count()).group_by(Property.status)
    if date_from:
        lq = lq.where(Lead.created_ts >= datetime.combine(date_from, datetime.min.time(), TZ))
        pq = pq.where(Property.created_at >= datetime.combine(date_from, datetime.min.time(), TZ))
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), TZ)
        lq, pq = lq.where(Lead.created_ts < end), pq.where(Property.created_at < end)
    leads = dict(db.execute(lq).all())
    props = dict(db.execute(pq).all())
    order = ["new", "operator_taken", "agent_assigned", "slots_sent", "time_chosen", "viewing_done", "thinking",
             "contract", "deal_pending", "rented", "refused"]
    reached = {}
    for i, st in enumerate(order[:-1]):  # leads that reached at least this stage (refused counted separately)
        reached[st] = sum(n for s, n in leads.items() if s in order[i:-1])
    return {"leads": leads, "leads_reached": reached, "leads_total": sum(leads.values()),
            "properties": props, "properties_total": sum(props.values())}


def _avg(xs: list[float]) -> int:
    return round(sum(xs) / len(xs)) if xs else 0


def listings_stats(db: Session) -> dict:
    """apps-script updateAnalyticsCache: Listings (all parsed posts) by district/agent/rooms with prices, and
    Active_Listings (status active) totals, exclusive share, by rooms/agent."""
    rows = db.execute(select(ChannelPost.district, ChannelPost.price, ChannelPost.rooms, ChannelPost.agent_name,
                             ChannelPost.status, ChannelPost.is_exclusive)).all()
    by_d: dict[str, list[float]] = {}
    counts, by_a, by_r, prices = {}, {}, {}, []
    for d, p, r, a, _, _ in rows:
        p = _f(p)
        if d:
            counts[d] = counts.get(d, 0) + 1
            by_d.setdefault(d, [])
            if p:
                by_d[d].append(p)
        if a:
            by_a[a] = by_a.get(a, 0) + 1
        if r:
            by_r[r] = by_r.get(r, 0) + 1
        if p:
            prices.append(p)
    districts = sorted(({"district": d, "count": counts[d], "avg_price": _avg(ps), "min_price": round(min(ps)) if ps else 0,
                         "max_price": round(max(ps)) if ps else 0} for d, ps in by_d.items()), key=lambda x: -x["count"])
    act = [(a, _f(p), r, ex) for _, p, r, a, st, ex in rows if st == "active" and a]
    act_agents, act_rooms = {}, {}
    for a, _, r, _ in act:
        act_agents[a] = act_agents.get(a, 0) + 1
        if r:
            act_rooms[r] = act_rooms.get(r, 0) + 1
    return {
        "listings": {"total": len(rows), "avg_price": _avg(prices), "by_district": districts, "by_agent": by_a, "by_rooms": by_r},
        "active": {"total": len(act), "avg_price": _avg([p for _, p, _, _ in act if p]),
                   "excl_pct": round(sum(1 for *_, ex in act if ex) / len(act) * 100) if act else 0, "by_rooms": act_rooms,
                   "top_agents": [{"name": n, "count": c} for n, c in sorted(act_agents.items(), key=lambda x: -x[1])]},
    }


def weekly_listings(db: Session, at: datetime | None = None) -> dict:
    """apps-script getWeeklyListingsStats: listings posted per agent this week vs last week; weeks start Monday 12:00
    Tbilisi time."""
    t = (at or now()).astimezone(TZ)
    mon = (t - timedelta(days=t.weekday())).replace(hour=12, minute=0, second=0, microsecond=0)
    if t < mon:
        mon -= timedelta(days=7)
    last, nxt = mon - timedelta(days=7), mon + timedelta(days=7)

    def build(a: datetime, b: datetime) -> dict:
        rows = db.execute(select(ChannelPost.agent_name, func.count()).where(
            ChannelPost.date >= a, ChannelPost.date < b, ChannelPost.agent_name.isnot(None), ChannelPost.agent_name != "")
            .group_by(ChannelPost.agent_name)).all()
        by = dict(rows)
        return {"total": sum(by.values()), "week_start": a.strftime("%d.%m"), "by_agent": by,
                "top_agents": [{"name": n, "count": c} for n, c in sorted(by.items(), key=lambda x: -x[1])]}
    return {"current": build(mon, nxt), "last_week": build(last, mon), "week_start": mon.strftime("%d.%m")}


def channel_posts(db: Session, start: date, end: date) -> dict:
    """«Посты в канал» (Stanislav 11-13): posts per agent in [start, end] (Tbilisi days), with exclusives. The agent is
    the user the post's hashtag resolved to, else the hashtag itself (an agent the CRM doesn't know yet)."""
    a = datetime.combine(start, datetime.min.time(), tzinfo=TZ)
    b = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    who = func.coalesce(User.name, func.nullif(ChannelPost.agent_name, ""), "без хэштега")
    rows = db.execute(select(ChannelPost.agent_id, who, func.count(), func.count().filter(ChannelPost.is_exclusive),
                             func.max(ChannelPost.date))
                      .outerjoin(User, User.id == ChannelPost.agent_id)
                      .where(ChannelPost.date >= a, ChannelPost.date < b)
                      .group_by(ChannelPost.agent_id, who).order_by(func.count().desc())).all()
    items = [{"agent_id": i, "name": n, "posts": c, "exclusive": ex, "last": last.isoformat() if last else None}
             for i, n, c, ex, last in rows]
    return {"from": start.isoformat(), "to": end.isoformat(), "total": sum(x["posts"] for x in items), "items": items}


# «В работе» tab = the board without its done columns (frontend lists.tsx WORK)
WORK_STATUSES = ("taken", "call_failed", "owner_confirmed", "agent_marked", "shoot_scheduled", "media_uploaded",
                 "review", "returned")


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def stats(db: Session, user: User, mine: bool = False) -> dict:
    """«Статистика» on «Главная» (Stanislav 11-11): where the objects / leads / deals are. Staff: the agency; an agent:
    his own (same scoping as the lists the numbers link to). The parsed-ads feed is shared, so it is never scoped."""
    staff = at_least(user, "operator") and not mine  # mine: a staff member's own numbers (works_as_agent) next to the agency's
    t = now().astimezone(TZ)
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    utc = lambda d: d.astimezone(timezone.utc).isoformat(timespec="seconds")  # listings/leads keep UTC ISO text
    prev = (t.month - 2) % 12 + 1, t.year - (t.month == 1)
    mine_p = () if staff else (Property.agent_id == user.id,)
    mine_l = () if staff else (Lead.agent_id == user.id,)
    mine_d = () if staff else (Deal.agent_id == user.id,)
    base = (Property.published_at.isnot(None),)
    from app.services.properties import _untaken
    linked = select(PropertyListing.listing_id).join(Property, Property.id == PropertyListing.property_id).where(
        Property.listing_id.is_distinct_from(PropertyListing.listing_id))
    feed = (*_untaken(), Listing.id.not_in(linked))  # = the «Новые объявления» feed (properties.new_listings)
    new_l = ("new", "operator_taken") if staff else ("agent_assigned",)
    open_l = (Lead.archived_at.is_(None), Lead.status.not_in(("rented", "refused", *new_l)))
    if not staff:  # an agent's board starts after the operator
        open_l += (Lead.status.not_in(("new", "operator_taken")),)
    return {
        "scope": "agency" if staff else "mine",
        "objects": {
            "work": _count(db, Property, Property.status.in_(WORK_STATUSES), Property.board_hidden_at.is_(None), *mine_p),
            "review": _count(db, Property, Property.status == "review", *mine_p),
            "published": _count(db, Property, Property.status == "published", *base, *mine_p),
            "rented": _count(db, Property, Property.status == "rented", *base, *mine_p),
            "archived": _count(db, Property, Property.status == "archived", *mine_p),
            "feed_today": _count(db, Listing, *feed, Listing.first_seen >= utc(day)),
            "feed_week": _count(db, Listing, *feed, Listing.first_seen >= utc(day - timedelta(days=6))),
        },
        "leads": {
            "new": _count(db, Lead, Lead.status.in_(new_l), Lead.archived_at.is_(None), *mine_l),
            "work": _count(db, Lead, *open_l, *mine_l),
            "viewings_today": _count(db, Lead, Lead.viewing_at >= day, Lead.viewing_at < day + timedelta(days=1),
                                     Lead.status.not_in(("refused",)), *mine_l),
            "rented_month": _count(db, Lead, Lead.status == "rented", Lead.updated_at >= utc(day.replace(day=1)), *mine_l),
        },
        "deals": {
            "month": _count(db, Deal, Deal.status.in_(LIVE), Deal.month == f"{t.month}/{t.year}", *mine_d),
            "prev_month": _count(db, Deal, Deal.status.in_(LIVE), Deal.month == f"{prev[0]}/{prev[1]}", *mine_d),
        },
        "contracts_expiring": _count(db, Deal, Deal.status == "confirmed", Deal.rent_to >= t.date(),
                                     Deal.rent_to <= t.date() + timedelta(days=30), *mine_d),
    }


def dashboard(db: Session, month: str | None = None) -> dict:
    y, m = month_bounds(month)
    mo = f"{m}/{y}"
    active_objects = db.scalar(select(func.count()).select_from(Property).where(Property.status == "published")) or 0
    channel_active = db.scalar(select(func.count()).select_from(ChannelPost).where(ChannelPost.status == "active")) or 0
    open_leads = db.scalar(select(func.count()).select_from(Lead).where(Lead.status.not_in(("rented", "refused")))) or 0
    overdue = db.scalar(select(func.count()).select_from(Lead).where(Lead.sla_due_at < now())) or 0
    last = db.scalars(select(Deal).where(Deal.status.in_(LIVE)).order_by(Deal.created_at.desc()).limit(10))
    names = dict(db.execute(select(User.id, User.name).where(FIELD_SQL | User.role.in_(STAFF))).all())
    return {
        "month": mo, "deals_month": deals_summary(db, mo), "deals_all": deals_summary(db),
        "active_objects": active_objects, "channel_active_listings": channel_active, "open_leads": open_leads,
        "sla_overdue": overdue, "monthly": monthly(db), "listings": listings_stats(db), "weekly_listings": weekly_listings(db), "leaderboard": leaderboard(db, mo),
        "leaderboard_all": leaderboard(db), "funnel": funnel(db), "response_times": response_times(db),
        "last_deals": [{"id": d.id, "agent": names.get(d.agent_id), "price": _f(d.price), "commission": _f(d.commission_total),
                        "platform": _f(d.platform_amount), "exclusive": d.is_exclusive, "status": d.status,
                        "date": d.created_at.astimezone(TZ).strftime("%d.%m.%y")} for d in last],
    }


# «Активность агента» (Stanislav 11-13): targets per 30 days and weights in %, one place for the API and the UI
ACTIVITY_DAYS = 30
ACTIVITY_TARGETS = {"new": 60, "active": 60, "deals": 5}
ACTIVITY_WEIGHTS = {"new": 40, "active": 30, "deals": 30}
ACTIVITY_START = datetime(2026, 11, 13, tzinfo=TZ)  # counts only new-CRM work from this day (old data inflated it)


def activity_score(new: int, active: int, deals: int) -> int:
    got = {"new": new, "active": active, "deals": deals}
    return round(sum(min(got[k] / t, 1) * ACTIVITY_WEIGHTS[k] for k, t in ACTIVITY_TARGETS.items()))


def _activity_since() -> tuple[datetime, bool]:
    """window start and whether it is clipped by ACTIVITY_START (the first 30 days of the new CRM)."""
    since = now() - timedelta(days=ACTIVITY_DAYS)
    return (ACTIVITY_START, True) if since < ACTIVITY_START else (since, False)


def _activity_counts(db: Session) -> tuple[dict, dict, dict]:
    """per agent: objects added in the CRM in the window, objects in work added since ACTIVITY_START,
    CRM-confirmed deals in the window. No channel posts / legacy objects / imported deals (11-13: they inflated it)."""
    since, _ = _activity_since()
    crm = Property.source_type.is_distinct_from("legacy")
    new = dict(db.execute(select(Property.agent_id, func.count()).where(crm, Property.created_at >= since)
                          .group_by(Property.agent_id)).all())
    active = dict(db.execute(select(Property.agent_id, func.count())
                             .where(crm, Property.created_at >= ACTIVITY_START, Property.status.not_in(("archived", "rented")))
                             .group_by(Property.agent_id)).all())
    deals = dict(db.execute(select(Deal.agent_id, func.count())
                            .where(Deal.status == "confirmed", Deal.source == "crm", Deal.confirmed_at >= since)
                            .group_by(Deal.agent_id)).all())
    return new, active, deals


def _activity(new: int, active: int, deals: int) -> dict:
    since, clipped = _activity_since()
    return {"score": activity_score(new, active, deals), "new": new, "active": active, "deals": deals,
            "targets": ACTIVITY_TARGETS, "weights": ACTIVITY_WEIGHTS, "days": ACTIVITY_DAYS,
            "since": since.astimezone(TZ).date().isoformat() if clipped else None}


def agents(db: Session, month: str | None = None) -> list[dict]:
    from app.services import reports, users
    y, m = month_bounds(month)
    mo = f"{m}/{y}"
    board = {r["id"]: r for r in leaderboard(db, mo, limit=1000)}
    counters = {r["user"]["id"]: r for r in reports.counters(db, mo)}
    # in work only (Irakli 11-13): not the archived old-CRM leads, not rented / archived objects
    lead_load = dict(db.execute(select(Lead.agent_id, func.count()).where(Lead.status.not_in(("rented", "refused")),
                                                                         Lead.archived_at.is_(None))
                                .group_by(Lead.agent_id)).all())
    props = dict(db.execute(select(Property.agent_id, func.count()).where(Property.status.not_in(("archived", "rented")))
                            .group_by(Property.agent_id)).all())
    act_new, act_active, act_deals = _activity_counts(db)
    out = []
    # «Команда» shows only working agents (Irakli 2026-11-09): a deactivated one stays in the history, not on the board
    for u in db.scalars(select(User).where(FIELD_SQL, User.is_active.is_(True)).order_by(User.name)):
        out.append({"id": u.id, "name": u.name, "first_name": u.first_name, "last_name": u.last_name, "username": u.username, "role": u.role, "is_active": u.is_active,
                    "mentor_id": u.mentor_id, **users.level_info(u), "deals_month": board.get(u.id, {}).get("deals", 0),
                    "agent_amount_month": board.get(u.id, {}).get("agent_amount", 0), "open_leads": lead_load.get(u.id, 0),
                    "properties": props.get(u.id, 0), "counters": counters.get(u.id),
                    "activity": _activity(act_new.get(u.id, 0), act_active.get(u.id, 0), act_deals.get(u.id, 0))})
    return out


# ---------------------------------------------------------------- «Статистика» (Stanislav 11-13, for David)
# The blocks of the old workbook sheet «TBILISI ANALYSIS RENT AND SALE» (docs/STATS-BLOCKS.md), live from the CRM:
# objects = properties added that month, clients = leads created, rent-outs / cash-in = deals by Deal.month.
STATS_MONTHS = 12
BUDGET_MAX = 20000  # a lead's «$N» above this is a sale price, not a monthly rent budget (the sheet summed rent only)


def _month_keys(y: int, m: int, n: int = STATS_MONTHS) -> list[tuple[int, int]]:
    k = y * 12 + m - 1
    return [((k - i) // 12, (k - i) % 12 + 1) for i in range(n - 1, -1, -1)]


def _ym(col):  # literals, not binds: the same expression must match in GROUP BY
    return func.to_char(func.timezone(literal_column(f"'{TZ}'"), col), literal_column("'YYYY-MM'"))


def _pct(a, b):
    return round(a / b * 100) if b else None


def month_stats(db: Session, month: str | None = None) -> dict:
    from sqlalchemy import Integer, case, cast
    y, m = month_bounds(month)
    keys = _month_keys(y, m)
    iso = [f"{a}-{b:02d}" for a, b in keys]
    cur, prev = iso[-1], iso[-2]
    start = datetime(keys[0][0], keys[0][1], 1, tzinfo=TZ)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=TZ)
    mo_start = datetime(y, m, 1, tzinfo=TZ)
    deal_mo = {f"{b}/{a}": f"{a}-{b:02d}" for a, b in keys}  # Deal.month «M/YYYY» → «YYYY-MM»

    ppm = Property.price / func.nullif(Property.area, 0)
    p_in = (Property.created_at >= start, Property.created_at < end)
    budget = cast(func.substring(Lead.request, r"\$(\d{2,6})"), Integer)
    budget = case((budget < BUDGET_MAX, budget))
    l_in = (Lead.created_ts >= start, Lead.created_ts < end)
    d_in = (Deal.status.in_(LIVE), Deal.month.in_(deal_mo))

    # ---- by month (the sheet's month rows: Published / Client's / Rent Out / Cash In)
    trend = {k: {"month": k, "objects": 0, "clients": 0, "budget_sum": 0, "rentouts": 0, "commission": 0, "platform": 0,
                 "agents": 0, "obj_median": 0, "budget_median": 0} for k in iso}
    # medians = the workbook's «Medium Price $$ Owner's / Client's» line charts (11-14); rent prices only (< $20k)
    med = lambda c: func.percentile_cont(0.5).within_group(c)  # noqa: E731
    rent_price = case((Property.price < BUDGET_MAX, Property.price))
    for k, n, pm_ in db.execute(select(_ym(Property.created_at), func.count(), med(rent_price)).where(*p_in)
                                .group_by(_ym(Property.created_at))).all():
        trend[k].update(objects=n, obj_median=round(_f(pm_)))
    for k, n, b, bm in db.execute(select(_ym(Lead.created_ts), func.count(), func.sum(budget), med(budget)).where(*l_in)
                                  .group_by(_ym(Lead.created_ts))).all():
        trend[k].update(clients=n, budget_sum=round(_f(b)), budget_median=round(_f(bm)))
    for mo, n, c, p, a in db.execute(select(Deal.month, func.count(), func.sum(Deal.commission_total),
                                            func.sum(Deal.platform_amount), func.sum(Deal.agent_amount))
                                     .where(*d_in).group_by(Deal.month)).all():
        trend[deal_mo[mo]].update(rentouts=n, commission=round(_f(c)), platform=round(_f(p)), agents=round(_f(a)))
    trend_l = list(trend.values())

    # ---- the month: totals
    pm = (Property.created_at >= mo_start, Property.created_at < end)
    lm = (Lead.created_ts >= mo_start, Lead.created_ts < end)
    dm = (Deal.status.in_(LIVE), Deal.month == f"{m}/{y}")
    obj = db.execute(select(func.count(), func.avg(Property.price), func.avg(ppm),
                            func.count().filter(Property.post_fields["deal"].astext == "Sale")).where(*pm)).one()
    cl = db.execute(select(func.count(), func.avg(budget), func.count(budget)).where(*lm)).one()
    by_type = {t: {"count": n, "commission": round(_f(c)), "avg_price": round(_f(p))} for t, n, c, p in db.execute(
        select(Deal.deal_type, func.count(), func.sum(Deal.commission_total), func.avg(Deal.price)).where(*dm)
        .group_by(Deal.deal_type)).all()}
    c_, p_ = trend[cur], trend[prev]
    summary = {
        "objects": obj[0], "objects_sale": obj[3], "objects_avg_price": round(_f(obj[1])), "objects_avg_ppm": round(_f(obj[2]), 2),
        "clients": cl[0], "clients_avg_budget": round(_f(cl[1])), "clients_with_budget": cl[2], "budget_sum": c_["budget_sum"],
        "rentouts": c_["rentouts"], "commission": c_["commission"], "platform": c_["platform"], "agents": c_["agents"],
        "by_type": by_type,
        "mom": {k: _pct(c_[k] - p_[k], p_[k]) for k in ("objects", "clients", "rentouts", "commission")},
    }

    # ---- by agent (the sheet's agent columns + the «Quality» summary)
    rows: dict = {}

    def put(aid, **kw):
        r = rows.setdefault(aid, {"id": aid, "objects": 0, "ppm": None, "clients": 0, "rentouts": 0, "commission": 0,
                                  "agent_amount": 0, "platform": 0})
        r.update(kw)
    for aid, n, a in db.execute(select(Property.agent_id, func.count(), func.avg(ppm)).where(*pm).group_by(Property.agent_id)).all():
        put(aid, objects=n, ppm=round(_f(a), 2) if a is not None else None)
    for aid, n in db.execute(select(Lead.agent_id, func.count()).where(*lm).group_by(Lead.agent_id)).all():
        put(aid, clients=n)
    for aid, n, c, a, p in db.execute(select(Deal.agent_id, func.count(), func.sum(Deal.commission_total),
                                             func.sum(Deal.agent_amount), func.sum(Deal.platform_amount))
                                      .where(*dm).group_by(Deal.agent_id)).all():
        put(aid, rentouts=n, commission=round(_f(c)), agent_amount=round(_f(a)), platform=round(_f(p)))
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_([k for k in rows if k]))).all())
    agents_l = []
    for aid, r in rows.items():
        conv = [x for x in (_pct(r["rentouts"], r["objects"]), _pct(r["rentouts"], r["clients"])) if x is not None]
        agents_l.append({**r, "name": names.get(aid) or "без агента", "share": _pct(r["agent_amount"], r["commission"]),
                         "obj_conv": _pct(r["rentouts"], r["objects"]), "client_conv": _pct(r["rentouts"], r["clients"]),
                         "quality": round(sum(conv) / len(conv)) if conv else None})
    agents_l.sort(key=lambda r: (-r["commission"], -r["rentouts"], -r["clients"]))

    # ---- where the clients came from (sheet: «Откуда пришел Клиент?»; old leads keep it in the note)
    src = func.coalesce(func.substring(Lead.client_note, literal_column("E'Откуда: ([^\\n]+)'")), Client.channel)
    sources = [{"source": s, "count": n} for s, n in db.execute(
        select(src, func.count()).select_from(Lead).join(Client, Client.id == Lead.client_id).where(*lm).group_by(src)
        .order_by(func.count().desc())).all()]

    # ---- prices by district × bedrooms: our objects of the month and the scraped market feed
    def grid(district, beds, price, area, *where):
        # grouped in Python: the parser stores English names (Saburtalo), the CRM Russian ones (Сабуртало) -> one row
        cells: dict = {}
        for d, bd, pr, ar in db.execute(select(district, func.least(beds, 4), price, area)
                                        .where(price > 0, district.isnot(None), *where)).all():
            cells.setdefault((districts.label(d) or d, str(bd) if bd is not None else "?"), []).append((_f(pr), ar))
        by: dict = {}
        for (d, bd), rows in cells.items():
            x = by.setdefault(d, {"district": d, "count": 0, "cells": {}})
            x["count"] += len(rows)
            ppm = [p / _f(ar) for p, ar in rows if ar and _f(ar) > 0]
            x["cells"][bd] = {"count": len(rows), "median": round(statistics.median(p for p, _ in rows)),
                              "ppm": round(sum(ppm) / len(ppm), 1) if ppm else None}
        return sorted(by.values(), key=lambda x: -x["count"])[:15]
    utc = lambda d: d.astimezone(timezone.utc).isoformat(timespec="seconds")
    prices = {"objects": grid(Property.district, Property.bedrooms, Property.price, Property.area, *pm,
                              Property.post_fields["deal"].astext.is_distinct_from("Sale")),
              "market": grid(Listing.district, Listing.bedrooms, Listing.price_usd, Listing.area,
                             Listing.first_seen >= utc(mo_start), Listing.first_seen < utc(end))}
    return {"month": cur, "summary": summary, "trend": trend_l, "agents": agents_l, "sources": sources, "prices": prices}
