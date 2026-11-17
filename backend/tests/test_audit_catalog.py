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
