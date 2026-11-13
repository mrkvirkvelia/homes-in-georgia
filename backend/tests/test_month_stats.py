"""Stanislav 11-13: «Статистика» — the old workbook's monthly blocks from CRM data (docs/STATS-BLOCKS.md)."""
from datetime import datetime

from app.models import Deal, Lead, Property
from app.services.common import TZ
from tests.conftest import auth, make_client, make_user


def test_month_stats_blocks(db, client):
    a, b, op = make_user(db, "agent", "Ann"), make_user(db, "agent", "Bob"), make_user(db, "operator")
    c = make_client(db)
    oct_, sep = datetime(2025, 10, 15, 12, tzinfo=TZ), datetime(2025, 9, 10, 12, tzinfo=TZ)
    for agent, price, area, at, dist, beds in ((a, 600, 50, oct_, "Vake", 1), (a, 1000, 100, oct_, "Vake", 2),
                                               (b, 800, 40, oct_, "Saburtalo", 1), (b, 500, 50, sep, "Vake", 1)):
        db.add(Property(agent_id=agent.id, price=price, area=area, created_at=at, district=dist, bedrooms=beds, status="archived"))
    for agent, req, note, at in ((a, "Rent, 1 bed, $700, Vake", "Откуда: Instagram", oct_), (a, "Sale, $150000", None, oct_),
                                 (b, "Rent, $500", "Откуда: Instagram", oct_), (None, None, None, oct_), (b, "$900", None, sep)):
        db.add(Lead(client_id=c.id, agent_id=agent.id if agent else None, request=req, client_note=note, status="new",
                    created_at=at.isoformat(), updated_at=at.isoformat(), created_ts=at))
    for agent, comm, ag, st, mo in ((a, 400, 360, "confirmed", "10/2025"), (a, 300, 210, "pending", "10/2025"),
                                    (b, 500, 350, "confirmed", "10/2025"), (b, 999, 1, "cancelled", "10/2025"),
                                    (b, 250, 175, "confirmed", "9/2025")):
        db.add(Deal(agent_id=agent.id, commission_total=comm, agent_amount=ag, platform_amount=comm - ag, status=st, month=mo,
                    price=comm * 2))
    db.commit()

    assert client.get("/api/analytics/stats?month=2025-10", headers=auth(a)).status_code == 403
    r = client.get("/api/analytics/stats?month=2025-10", headers=auth(op)).json()
    s = r["summary"]
    assert (s["objects"], s["clients"], s["rentouts"], s["commission"]) == (3, 4, 3, 1200)
    assert s["clients_avg_budget"] == 600 and s["budget_sum"] == 1200  # the $150000 sale price is not a rent budget
    assert s["objects_avg_ppm"] == round((12 + 10 + 20) / 3, 2)
    assert s["mom"]["rentouts"] == 200 and s["mom"]["objects"] == 200  # 1 → 3
    assert [t["month"] for t in r["trend"]][-2:] == ["2025-09", "2025-10"] and len(r["trend"]) == 12
    assert r["trend"][-2]["rentouts"] == 1 and r["trend"][-2]["clients"] == 1
    ann = next(x for x in r["agents"] if x["name"] == "Ann")
    assert (ann["objects"], ann["clients"], ann["rentouts"], ann["commission"], ann["agent_amount"]) == (2, 2, 2, 700, 570)
    assert ann["share"] == 81 and ann["obj_conv"] == 100 and ann["client_conv"] == 100 and ann["quality"] == 100
    assert next(x for x in r["agents"] if x["id"] is None)["clients"] == 1
    assert r["sources"][0] == {"source": "Instagram", "count": 2}
    vake = next(x for x in r["prices"]["objects"] if x["district"] == "Vake")
    assert vake["cells"]["1"] == {"count": 1, "median": 600, "ppm": 12.0} and vake["count"] == 2
    assert r["prices"]["market"] == []
