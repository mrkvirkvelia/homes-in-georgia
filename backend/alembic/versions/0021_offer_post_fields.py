"""sale_objects.post_fields (the rent objects' tags instead of the site's words), properties.site_hidden

The sale form is the rent generator's now (Stanislav 11-15): kind / headline / metro / approx / building / condition /
heating / amenities move into post_fields, words the generator has no tag for stay in post_fields.site_extra (the site
still shows them, services/site_feed.py). Self-contained: the maps are copied here, not imported.

Revision ID: 0021
Revises: 0020
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KIND = {"apartment": "Apartment", "house": "House", "commercial": "Commercial", "land": "Land"}
BUILDING = {"new": "NewBuilding", "old": "OldBuilding", "historical": "HistoricalBuilding"}
HEATING = {"central": "CentralHeating", "gas": "GasHeating", "electric": "ElectricalHeating"}
FRAME = {"white_frame": "WhiteFrame", "green_frame": "GreenFrame", "black_frame": "BlackFrame", "renovated": "FullyRenovated"}
DESIGN = {"mixed": "Mixed", "old": "Old"}
AMENITY = {"balcony": "Balcony", "terrace": "Terrace", "courtyard": "Courtyard", "wifi": "WiFi", "tv": "TV",
           "dishwasher": "Dishwasher", "stove": "Stove", "microwave": "Microwave", "washer": "WashingMachine",
           "vacuum": "VacuumCleaner", "fireplace": "Fireplace", "elevator": "Elevator", "oven": "Oven",
           "parking": "ParkingPlace", "conditioner": "Conditioner", "bath": "Bath", "shower": "Shower"}
METRO = {"Liberty Square": "LibertySquare", "Rustaveli": "Rustaveli", "Marjanishvili": "Marjanishvili",
         "Station Square": "StationSquare", "Tsereteli": "Tsereteli", "Gotsiridze": "Gotsiridze",
         "Nadzaladevi": "Nadzaladevi", "Didube": "Didube", "Grmagele": "Grmagele", "Guramishvili": "Guramishvili",
         "Sarajishvili": "Sarajishvili", "Akhmeteli Theatre": "AhmeteliTheatre", "Technical University": "STUniversity",
         "Vazha-Pshavela": "VazhaPshavela", "Delisi": "Delisi", "State University": "TCUniversity",
         "Medical University": "MCUniversity", "Avlabari": "AvlabariMetro", "Isani": "IsaniMetro",
         "300 Aragveli": "300Aragveli", "Samgori": "SamgoriMetro", "Varketili": "Varketili"}
OLD = ("kind", "headline", "metro", "approx", "building", "condition", "heating", "amenities")


def tags(r) -> dict:
    f, extra = {"deal": "Sale", "prop_type": KIND.get(r.kind, "Apartment")}, {}
    for col, m in (("building", BUILDING), ("heating", HEATING), ("metro", METRO)):
        v = getattr(r, col)
        if v and v in m:
            f[col] = m[v]
        elif v:
            extra[col] = v
    if r.condition in FRAME:
        f["condition"] = FRAME[r.condition]
    elif r.condition in DESIGN:
        f["design"] = DESIGN[r.condition]
    elif r.condition:
        extra["condition"] = r.condition
    am = r.amenities or []
    if known := [AMENITY[a] for a in am if a in AMENITY]:
        f["amenities"] = known
    if rest := [a for a in am if a not in AMENITY]:
        extra["amenities"] = rest
    if r.headline:
        f["headline"] = r.headline
    if r.approx:
        f["approx"] = True
    if extra:
        f["site_extra"] = extra
    return f


def upgrade() -> None:
    op.add_column("properties", sa.Column("site_hidden", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("sale_objects", sa.Column("post_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    conn = op.get_bind()
    for r in conn.execute(sa.text(f"SELECT id, {', '.join(OLD)} FROM sale_objects")).all():
        conn.execute(sa.text("UPDATE sale_objects SET post_fields = CAST(:f AS jsonb) WHERE id = :id"),
                     {"f": json.dumps(tags(r)), "id": r.id})
    for c in OLD:
        op.drop_column("sale_objects", c)


def downgrade() -> None:
    # ponytail: the columns come back empty; the tags stay in post_fields
    txt = lambda n, **kw: sa.Column(n, sa.Text, **kw)  # noqa: E731
    for col in (txt("kind", nullable=False, server_default="apartment"), txt("headline"), txt("metro"),
                sa.Column("approx", sa.Boolean, nullable=False, server_default=sa.text("false")),
                txt("building"), txt("condition"), txt("heating"),
                sa.Column("amenities", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))):
        op.add_column("sale_objects", col)
    op.drop_column("sale_objects", "post_fields")
    op.drop_column("properties", "site_hidden")
