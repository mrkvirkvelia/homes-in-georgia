"""Управление → Ключи → Расходы: Apify runs + AI tokens summed for today / week / month, no network."""
import json
import time
from datetime import datetime, timezone

from app.api import content
from app.models import Setting
from tests.conftest import auth, make_user


def test_spend(db, client, monkeypatch):
    monkeypatch.setattr(content, "_apify_accounts", lambda: [{"tail": "ab12", "used_usd": 4.68, "limit_usd": 5, "cycle_end": "2026-11-29", "error": None}])
    monkeypatch.setattr(content, "_proxyapi_balance", lambda: None)
    now = time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.add(Setting(key="source_runs", value=json.dumps({"facebook": [[now - 5 * 86400, 0.1, 9, 6], [now, 0.05, 3, 6]], "ss": [[now, 0.02, 1, 6]]})))
    db.add(Setting(key="llm_usage", value=json.dumps({today: {"gpt-4.1-mini": [3, 1_000_000, 100_000], "weird": [1, 5, 5]}, "1999-01-01": {"gpt-4.1-mini": [9, 9, 9]}})))
    db.commit()
    admin = make_user(db, "superadmin")
    r = client.get("/api/spend", headers=auth(admin)).json()
    assert r["apify"]["today_usd"] == 0.07 and r["apify"]["week_usd"] == 0.17 and r["apify"]["by_source_week"]["facebook"] == 0.15
    assert r["apify"]["accounts"][0]["used_usd"] == 4.68
    t = r["ai"]["today"]
    assert t["calls"] == 4 and t["prompt"] == 1_000_005 and t["usd"] == 0.56 and t["unpriced"] == ["weird"]
    assert r["ai"]["month"]["calls"] == 4  # 1999 is not this month
    assert client.get("/api/spend", headers=auth(make_user(db, "operator"))).status_code == 403
