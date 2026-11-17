"""Audit fixes: the catalog row's `pets` column (the bot's hard filter) and one lead per client per object."""
import json

from app.models import Lead, Listing, Property, PropertyMedia
from app.services import catalog, leads
from tests.conftest import make_client, make_listing


def _object(db, pets="NotAllowed", listing_id=None):
    p = Property(status="published", source_type="legacy", district="Vake", address="5 Abashidze St", price=700,
                 bedrooms=2, area=80, floor=4, listing_id=listing_id, post_url="https://t.me/rent_tbilisi_ge/9",
                 post_message_id="9", post_fields={"prop_type": "Apartment", "pets": pets})
    db.add(p)
    db.flush()
    db.add(PropertyMedia(property_id=p.id, path="legacy/x/1.jpg", kind="photo", position=0))
    db.commit()
    return p


def test_catalog_row_writes_pets_column(db):
    p = _object(db)
    assert catalog.sync_all(db) == 1
    row = db.get(Listing, catalog.catalog_id(p.id))
    assert json.loads(row.details)["pets"] == "not_allowed" and row.pets == "нет"
    row.pets = None  # a row synced before the column was written: the next sync fills it in
    db.commit()
    assert catalog.sync_all(db) == 1 and db.get(Listing, row.id).pets == "нет"
    assert catalog.sync_all(db) == 0
    p.post_fields = {**p.post_fields, "pets": "Allowed"}
    db.commit()
    assert catalog.sync_all(db) == 1 and db.get(Listing, row.id).pets == "да"
    p.post_fields = {"prop_type": "Apartment"}  # not stated: unknown, the filter lets it pass
    db.commit()
    assert catalog.sync_all(db) == 1 and db.get(Listing, row.id).pets is None


def test_post_button_resolves_the_catalog_row(db):
    manual = _object(db)  # created in the CRM by hand: no source ad
    ad = make_listing(db, "ss7001")
    taken = _object(db, listing_id=ad.id)
    catalog.sync_all(db)
    assert leads.object_listing_id(db, manual.id) == catalog.catalog_id(manual.id)
    assert leads.object_listing_id(db, taken.id) == catalog.catalog_id(taken.id)
    db.delete(db.get(Listing, catalog.catalog_id(taken.id)))  # not synced yet: the ad it was taken from
    db.commit()
    assert leads.object_listing_id(db, taken.id) == ad.id
    manual.status = "archived"
    db.commit()
    assert leads.object_listing_id(db, manual.id) is None and leads.object_listing_id(db, 999999) is None


def test_one_lead_per_client_and_object(db):
    customer = make_client(db)
    ad = make_listing(db, "ss7002")
    p = _object(db, listing_id=ad.id)
    catalog.sync_all(db)
    old = leads.create_from_like(db, customer.id, ad.id)  # an older lead under the ad's id (the post button)
    lead = leads.create_from_like(db, customer.id, catalog.catalog_id(p.id))  # ❤️ in the search
    assert lead.id == old.id and db.query(Lead).count() == 1
    lead.status = "refused"
    db.commit()
    again = leads.create_from_like(db, customer.id, catalog.catalog_id(p.id))
    assert again.id == old.id and again.status == "new" and db.query(Lead).count() == 1
    other = make_client(db, external_id=5550002)
    assert leads.create_from_like(db, other.id, catalog.catalog_id(p.id)).id != old.id  # other clients: their own
