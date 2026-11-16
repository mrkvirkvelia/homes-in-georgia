"""Управление → Ключи → Расходы: Apify runs + AI tokens summed for today / week / month, no network."""
import json
import time
from datetime import datetime, timezone

from app.api import content
from app.models import Setting
from tests.conftest import auth, make_user


def test_spend(db, client, monkeypatch):
    monkeypatch.setattr(content, "_apify_accounts", lambda: [{"tail": "ab12", "used_usd": 4.68, "limit_usd": 5, "cycle_end": "2026-11-29", "error": None}])
    monkeypatch.setattr(content, "_ai_balance", lambda: {"balance_usd": 9.5, "used_usd": 0.5})
    monkeypatch.setattr(content, "_openrouter_prices", lambda: {"google/gemma": (1e-7, 2e-7)})
    now = time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.add(Setting(key="source_runs", value=json.dumps({"facebook": [[now - 5 * 86400, 0.1, 9, 6], [now, 0.05, 3, 6]], "ss": [[now, 0.02, 1, 6]]})))
    db.add(Setting(key="llm_usage", value=json.dumps({today: {"gpt-4.1-mini": [3, 1_000_000, 100_000], "weird": [1, 5, 5],
                                                          "google/gemma": [10, 1000, 100, 0.25, 1000, 0]}, "1999-01-01": {"gpt-4.1-mini": [9, 9, 9]}})))
    db.add(Setting(key="llm_purpose", value=json.dumps({today: {
        "index_competitor": {"google/gemma": [3, 1000, 500, 0.3, 0, 0]},
        "search_query": {"google/gemma": [2, 100, 10, 0.01, 0, 0]}, "search_pick": {"google/gemma": [2, 200, 20, 0.03, 0, 0]}}})))
    db.commit()
    admin = make_user(db, "superadmin")
    r = client.get("/api/spend", headers=auth(admin)).json()
    assert r["apify"]["today_usd"] == 0.07 and r["apify"]["week_usd"] == 0.17 and r["apify"]["by_source_week"]["facebook"] == 0.15
    assert r["apify"]["accounts"][0]["used_usd"] == 4.68
    t = r["ai"]["today"]
    # gpt-4.1-mini at list price 0.56; gemma: 0.25 reported by OpenRouter + 1000 unpriced prompt tokens at its list price
    assert t["calls"] == 14 and t["prompt"] == 1_001_005 and t["usd"] == 0.8101 and t["unpriced"] == ["weird"]
    assert t["estimated"] and {m["model"]: m["usd"] for m in t["models"]}["google/gemma"] == 0.2501
    assert r["ai"]["month"]["calls"] == 14 and r["ai"]["week"]["calls"] == 14  # 1999 is not this month
    assert r["ai"]["balance"]["balance_usd"] == 9.5
    p = r["ai"]["purposes"]["today"]
    assert [x["purpose"] for x in p["rows"]] == ["index_competitor", "search_pick", "search_query"]
    assert p["rows"][0] == {"purpose": "index_competitor", "calls": 3, "tokens": 1500, "completion": 500, "usd": 0.3}
    assert p["searches"] == 2 and p["per_search_usd"] == 0.02  # (0.01 + 0.03) / 2 picks
    assert r["ai"]["purposes"]["month"]["rows"] == p["rows"]
    assert client.get("/api/spend", headers=auth(make_user(db, "operator"))).status_code == 403
