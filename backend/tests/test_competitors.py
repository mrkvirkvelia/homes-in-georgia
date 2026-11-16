"""Sources marked «Конкурент»: their ads live only in «Объекты → База → Конкуренты», the parser loads their history once."""
import json
import os
import sys

import pytest

from app.config import REPO_ROOT
from app.models import Source
from app.services.errors import DomainError
from app.services import properties as P
from tests.conftest import auth, make_listing, make_user


def _rival(db, kind="tg_competitor", key="rival_flats", url=None, **opts):
    s = Source(kind=kind, key=key, url=url or f"https://t.me/{key}", options=json.dumps({"competitor": True, **opts}))
    db.add(s)
    db.commit()
    return s


def test_competitor_ads_only_in_their_tab(db, client):
    agent = make_user(db, "agent")
    _rival(db)
    make_listing(db, "ss1", dup_sources='["tg:rival_flats", "tg:rival_flats"]')  # the owner's ad, the rival reposted it
    make_listing(db, "tg_rival_flats_7", source="tg:rival_flats", status="rejected", address="ул. Барнови 5")
    make_listing(db, "tg_friend_8", source="tg:friend")  # a channel not marked: our feed as before

    feed = client.get("/api/listings/new", headers=auth(agent)).json()
    assert {x["id"] for x in feed["items"]} == {"ss1", "tg_friend_8"}
    assert next(x for x in feed["items"] if x["id"] == "ss1")["at_competitor"] == ["tg:rival_flats"]

    rivals = client.get("/api/listings/new", params={"competitor": 1, "q": "Барнови"}, headers=auth(agent)).json()
    assert [x["id"] for x in rivals["items"]] == ["tg_rival_flats_7"] and rivals["total"] == 1
    facets = client.get("/api/listings/new/facets", params={"competitor": 1}, headers=auth(agent)).json()
    assert facets["sources"] == [{"value": "tg:rival_flats", "count": 1}]
    assert "tg:rival_flats" not in {x["value"] for x in client.get("/api/listings/new/facets", headers=auth(agent)).json()["sources"]}
    with pytest.raises(DomainError):  # not our inventory: never taken into work (so never published / on the site)
        P.take(db, "tg_rival_flats_7", agent)


def test_backfill_once_then_keeps_updating(db, tmp_path, monkeypatch):
    sys.path.append(str(REPO_ROOT / "bot"))
    import db as botdb
    botdb.URL = None  # DATABASE_URL = the backend test DB (conftest)
    s = _rival(db)
    _rival(db, "fb_group", "123", url="https://facebook.com/groups/123")
    db.add(Source(kind="tg_competitor", key="friend", url="https://t.me/friend", options="{}"))
    db.commit()
    monkeypatch.chdir(tmp_path)
    os.makedirs("raw")

    cfg = botdb.export_sources(str(tmp_path / "sources.json"))
    tg = {c["username"]: c for c in cfg["telegram_channels"]}
    assert tg["rival_flats"]["backfill"] == botdb.BACKFILL["telegram"] and "backfill" not in tg["friend"]
    assert cfg["facebook_groups"][0]["backfill"] == {"posts": 300, "days": 365}

    open(botdb.backfill_mark("rival_flats"), "w").write("2026-11-16T10:00:00+00:00")  # what the fetcher writes
    cfg = botdb.export_sources(str(tmp_path / "sources.json"))
    assert "backfill" not in {c["username"]: c for c in cfg["telegram_channels"]}["rival_flats"]
    db.refresh(s)
    assert json.loads(s.options)["backfilled_at"] == "2026-11-16T10:00:00+00:00"


def test_sync_keeps_competitor_ads_out_of_the_bot(db, tmp_path):
    sys.path.append(str(REPO_ROOT / "bot"))
    import db as botdb
    botdb.URL = None
    item = {"id": "tg_rival_flats_9", "source": "tg:rival_flats", "owner_id": "tg:rival_flats", "urls": ["https://t.me/rival_flats/9"],
            "price_usd": 900, "area": 60.0, "floor": 3, "bedrooms": 2, "address": "Барнови 5", "district": "Ваке", "latlng": None,
            "photos": [], "text": "Сдаётся", "agent_reasons": [], "competitor": True}
    f = tmp_path / "listings.json"
    f.write_text(json.dumps([item]))
    botdb.sync(str(f), str(tmp_path / "none.json"), full=False)
    db.expire_all()
    from app.models import Listing
    assert db.get(Listing, "tg_rival_flats_9").status == "rejected"  # the bot's search and review queue skip it


def test_competitor_filter_ours(db, client):
    from app.models import PropertyListing
    agent = make_user(db, "agent")
    _rival(db)
    make_listing(db, "ss1")
    make_listing(db, "tg_rival_flats_7", source="tg:rival_flats")
    make_listing(db, "tg_rival_flats_8", source="tg:rival_flats")
    p = P.take(db, "ss1", agent)
    db.add(PropertyListing(property_id=p.id, listing_id="tg_rival_flats_7", source="tg:rival_flats"))
    db.commit()
    ids = lambda **kw: {x["id"] for x in client.get("/api/listings/new", params={"competitor": 1, **kw}, headers=auth(agent)).json()["items"]}
    assert ids() == {"tg_rival_flats_7", "tg_rival_flats_8"}
    assert ids(flag="ours") == {"tg_rival_flats_7"}
    assert ids(flag="not_ours") == {"tg_rival_flats_8"}
