"""hge.ge's own counter: the site posts events to /api/public/site/events, CRM «Аналитика» (superadmins only) reads the report."""
import json

import pytest

from app.models import SiteEvent
from app.services import site_analytics
from tests.conftest import auth, make_user


@pytest.fixture(autouse=True)
def _no_cache():
    site_analytics.clear_cache()
    yield
    site_analytics.clear_cache()


def ev(t, v="v1", s="s1", **kw):
    return {"t": t, "v": v, "s": s, "src": "instagram", "dev": "mobile", "lang": "ru", "th": "light", "p": "/", **kw}


def post(client, events, raw=None):
    # the site sends text/plain (no CORS preflight; sendBeacon does the same)
    return client.post("/api/public/site/events", content=raw if raw is not None else json.dumps({"events": events}),
                       headers={"Content-Type": "text/plain"})


def test_events_in_report_out(db, client):
    r = post(client, [
        ev("pageview", nw=True),
        ev("listing", l="o1", sv="rent", ag="Nino"),
        ev("contact", l="o1", sv="rent", ag="Nino", x={"ch": "whatsapp"}),
        ev("fav", l="o1", x={"on": True}),
        ev("search", sv="rent", x={"q": "beds=2&district=Vake&sort=new", "n": 0}),
        ev("perf", x={"load": 1200, "lcp": 900}),
        ev("pageview", v="v2", s="s2", src="direct", dev="desktop"),
        ev("bogus"),  # unknown type: dropped
    ])
    assert r.json() == {"ok": True, "n": 7}

    h = auth(make_user(db, "superadmin"))
    rep = client.get("/api/analytics/site", params={"days": 7}, headers=h).json()
    t = rep["totals"]
    assert (t["visitors"], t["newVisitors"], t["sessions"], t["listingViews"], t["contacts"], t["favs"]) == (2, 1, 2, 1, 1, 1)
    assert t["conversion"] == 50.0
    assert rep["contactsBy"] == {"whatsapp": 1}
    assert rep["bestListings"][0]["id"] == "o1" and rep["agents"][0]["name"] == "Nino"
    assert rep["zeroSearches"][0]["name"] == "rent · beds=2 · district=Vake"
    assert {s["name"] for s in rep["sources"]} == {"instagram", "direct"}
    assert rep["devices"] == {"mobile": 1, "desktop": 1} and rep["perf"]["loadMedian"] == 1200
    assert rep["daily"] and sum(d["contacts"] for d in rep["daily"]) == 1


def test_public_endpoint_is_strict(db, client):
    assert post(client, None, raw="not json").json()["n"] == 0
    assert post(client, None, raw="x" * 70000).json()["n"] == 0
    assert post(client, [ev("pageview")] * 80).json()["n"] == 50  # one batch at most
    post(client, [ev("pageview", v="x" * 500, p="/" + "a" * 900)])
    row = db.query(SiteEvent).order_by(SiteEvent.id.desc()).first()
    assert len(row.visitor) == 40 and len(row.path) == 200


def test_only_superadmins_see_site_analytics(db, client):
    for role in ("admin", "operator", "agent", "recruit"):
        assert client.get("/api/analytics/site", headers=auth(make_user(db, role))).status_code == 403
    assert client.get("/api/analytics/site").status_code == 401
    r = client.get("/api/analytics/site", params={"days": 5000}, headers=auth(make_user(db, "superadmin")))
    assert r.status_code == 200 and r.json()["period"]["days"] == 7  # unknown period → 7 days


def test_only_errors_of_our_own_scripts_are_reported(db, client):
    post(client, [
        ev("error", x={"msg": "TypeError: x is undefined", "at": "page-3f2a.js:12"}),
        ev("error", s="s2", x={"msg": "TypeError: undefined is not an object (evaluating 'window.webkit.messageHandlers')", "at": ":0"}),
        ev("error", s="s3", x={"msg": "TypeError: window.ethereum.selectedAddress = undefined", "at": "listing:5"}),
        ev("error", s="s4", x={"msg": "boom", "at": "promise"}),
    ])
    names = [e["name"] for e in site_analytics.report(db, 7, fresh=True)["errors"]]
    assert names == ["TypeError: x is undefined"]
