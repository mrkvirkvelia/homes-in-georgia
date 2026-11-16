"""Stanislav 11-16 «закрой чужие карточки»: an agent opening another agent's / a platform object's card or its reads gets
404 (not 403); his own object and one tied to his lead, deal or contract stay open; staff see everything."""
from app.models import Contract, Deal, Lead, Property
from tests.conftest import auth, make_client, make_user


def test_foreign_cards_closed(db, client):
    me = make_user(db, "agent", "Заза")
    other = make_user(db, "agent", "Тамара")
    rec = make_user(db, "recruit", "Нико")
    op = make_user(db, "operator", "Нино")
    mine = Property(address="Мой 1", agent_id=me.id, status="taken")
    foreign = Property(address="Чужой 2", agent_id=other.id, status="published")
    platform = Property(address="Платформа 3", agent_id=None, status="published")
    by_lead, by_deal, by_contract = (Property(address=f"Связан {i}", agent_id=other.id, status="published") for i in range(3))
    db.add_all([mine, foreign, platform, by_lead, by_deal, by_contract])
    db.commit()
    cl = make_client(db)
    db.add_all([Lead(client_id=cl.id, property_id=by_lead.id, agent_id=me.id, status="new", created_at="2026-11-16", updated_at="2026-11-16"),
                Deal(property_id=by_deal.id, agent_id=me.id, status="draft"),
                Contract(property_id=by_contract.id, kind="rent", lang="RU", html="<p>x</p>", created_by=me.id)])
    db.commit()

    from app.services.properties import media_root
    for p in (foreign, platform, mine):
        f = media_root() / "properties" / str(p.id) / "x.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\xff\xd8\xff")
    assert client.get(f"/api/media/properties/{mine.id}/x.jpg", headers=auth(me)).status_code == 200
    assert client.get(f"/api/media/properties/{foreign.id}/x.jpg", headers=auth(op)).status_code == 200
    reads = ("", "/history", "/demand", "/elsewhere", "/post", "/contract")
    for who in (me, rec):
        for p in (foreign, platform):
            for r in reads:
                res = client.get(f"/api/properties/{p.id}{r}", headers=auth(who))
                want = 403 if who is rec and r == "/contract" else 404  # recruits: no contracts at all (role, not object)
                assert res.status_code == want, (who.role, p.address, r, res.status_code)
            res = client.get(f"/api/media/properties/{p.id}/x.jpg?p=1", headers=auth(who))
            assert res.status_code == 404
            res = client.get(f"/api/media/previews/properties/{p.id}/x.jpg.webp", headers=auth(who))
            assert res.status_code == 404
    for p in (mine, by_lead, by_deal, by_contract):
        res = client.get(f"/api/properties/{p.id}", headers=auth(me))
        assert res.status_code == 200, p.address
        assert client.get(f"/api/properties/{p.id}/history", headers=auth(me)).status_code == 200
    for p in (foreign, platform, by_lead):
        assert client.get(f"/api/properties/{p.id}", headers=auth(op)).status_code == 200

    # the deal picker still lists another agent's object (blocked), and says whether «Открыть» works
    items = client.get(f"/api/properties/deal-search?pid={platform.id}", headers=auth(me)).json()["items"]
    assert items and items[0]["can_open"] is False
    items = client.get(f"/api/properties/deal-search?pid={mine.id}", headers=auth(me)).json()["items"]
    assert items[0]["can_open"] is True
