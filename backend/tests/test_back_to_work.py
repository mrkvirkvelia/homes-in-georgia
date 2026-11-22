"""David 11-22 #8462: an archived («Неактуально») object comes back to work — by «Дубль: это он» on its fresh ad, or by
«Снова в работу» of the agent its owner was handed to; that agent hears of the transfer from the bot."""
from app.models import Owner, Property
from app.services import properties as P
from app.services import similar
from tests.conftest import make_listing, make_user


def _archived(db, agent, owner_agent=None):
    o = Owner(name="Георгий", phone="+995599133859", agent_id=owner_agent.id if owner_agent else None)
    db.add(o)
    db.flush()
    p = Property(status="archived", archive_reason="not_actual", agent_id=agent.id, owner_id=o.id, address="11 Kote Meskhi St",
                 source_type="legacy", bedrooms=1, area=80, floor=2, price=800)
    db.add(p)
    db.commit()
    return p, o


def test_duplicate_of_an_archived_object_brings_it_back(db):
    david, arthur = make_user(db, "admin", "David"), make_user(db, "agent", "Arthur")
    p, o = _archived(db, david)
    make_listing(db, "lv1", source="livo.ge")
    r = similar.decide(db, "l:lv1", f"p:{p.id}", True, arthur)
    db.expire_all()
    assert r["revived"] == p.id and db.get(Property, p.id).status == "taken" and db.get(Property, p.id).agent_id == arthur.id
    assert db.get(Owner, o.id).agent_id == arthur.id


def test_owner_of_another_agent_stops_it_then_the_transfer_lets_him(db, sent):
    david, arthur = make_user(db, "admin", "David"), make_user(db, "agent", "Arthur")
    zaza = make_user(db, "agent", "Zaza")
    p, o = _archived(db, david, owner_agent=zaza)
    make_listing(db, "lv2", source="livo.ge")
    r = similar.decide(db, "l:lv2", f"p:{p.id}", True, arthur)
    assert r["revived"] is None and r["owner_taken"] and db.get(Property, p.id).status == "archived"
    P.transfer_owner(db, o.id, arthur.id, make_user(db, "operator", "Оператор"))
    assert any(n == "owner_transferred" and a[0] == arthur.id for n, a in sent)
    q = P.resume(db, p.id, arthur)  # «Снова в работу» of the owner's agent
    assert (q.status, q.agent_id) == ("taken", arthur.id)


def test_the_owners_other_flat_in_the_house_goes_on_after_the_agent_says_so(db, client):
    """Irakli 11-22: same owner, same house — another flat; «Это другая квартира» lets it go to review."""
    import pytest
    from app.services.errors import DomainError
    agent = make_user(db, "agent", "Ираклий")
    o = Owner(name="Нино", phone="+995599100200")
    db.add(o)
    db.flush()
    other = Property(status="published", owner_id=o.id, address="12 Gabriel Isakadze St", agent_id=agent.id)
    p = Property(status="media_uploaded", owner_id=o.id, address="12 Gabriel Isakadze St", agent_id=agent.id)
    db.add_all([other, p])
    db.commit()
    import unittest.mock as um
    with um.patch.object(P, "media", lambda *a: [1]), um.patch.object(P, "require_min_photos", lambda *a: None), \
            um.patch.object(P, "missing_fields", lambda *a: []), um.patch.object(P, "missing_owner_docs", lambda *a: []):
        with pytest.raises(DomainError) as e:
            P.submit_for_review(db, p.id, agent)
        assert e.value.code == "object_exists" and e.value.data["property_id"] == other.id
        assert P.submit_for_review(db, p.id, agent, other_flat=True).status == "review"


def test_a_transfer_takes_the_dropped_archived_object_along(db):
    david, arthur = make_user(db, "admin", "David"), make_user(db, "agent", "Arthur")
    p, o = _archived(db, david, owner_agent=david)
    P.transfer_owner(db, o.id, arthur.id, david)
    db.expire_all()
    q = db.get(Property, p.id)
    assert q.agent_id == arthur.id and P.can_open(db, q, arthur)  # in his archive, the card opens
