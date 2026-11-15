"""Sale objects become properties (post_fields.deal = Sale); properties.site_hidden

Stanislav 11-15: no separate «Продажа» section, a sale is an object like a rent one («Объекты», switch Аренда /
Продажа). Every sale_objects row is copied into properties with its photos / video (property_media) and its facts as
the generator's tags; post_fields.offer_ident keeps the old site id "s<id>" (links keep resolving, site_feed.find), and
post_fields.site_id the old site's id. sale_objects stays, unused: drop it in a later migration once prod is checked.
Self-contained: the maps are copied here, not imported. site_hidden: «Снять с сайта» keeps an object published but
off hge.ge.

Revision ID: 0021
Revises: 0020
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

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


def tags(r) -> dict:
    """A sale_objects row -> post_fields (the rent generator's vocabulary); words without a tag go to site_extra."""
    f, extra = {"deal": "Sale", "service": r.service, "offer_ident": f"s{r.id}", "prop_type": KIND.get(r.kind, "Apartment")}, {}
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
    for k, v in (("headline", r.headline), ("site_id", r.site_id), ("completion", r.completion),
                 ("sale_price", int(r.price) if r.price is not None else None), ("approx", r.approx or None)):
        if v:
            f[k] = v
    if extra:
        f["site_extra"] = extra
    return f


def upgrade() -> None:
    op.add_column("properties", sa.Column("site_hidden", sa.Boolean, nullable=False, server_default=sa.text("false")))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT * FROM sale_objects ORDER BY id")).all()
    for r in rows:
        status = {"published": "published", "archived": "archived"}.get(r.status, "media_uploaded")
        pid = conn.execute(sa.text("""
            INSERT INTO properties (source_type, status, agent_id, address, district, lat, lng, price, currency, bedrooms,
                area, floor, total_floors, description, is_exclusive, post_fields, post_url, published_at, verified_at,
                archive_reason, archived_at, created_at, updated_at)
            VALUES (:src, :status, :agent, :title, :district, :lat, :lng, :price, :currency, :rooms, :area, :floor, :floors,
                :description, :excl, CAST(:pf AS jsonb), :post_url, :pub, :pub, :reason, :arch, :created, :updated)
            RETURNING id"""), {
            "src": "channel" if r.site_id else "direct", "status": status, "agent": r.agent_id, "title": r.title,
            "district": r.district, "lat": r.lat, "lng": r.lng, "price": r.price, "currency": r.currency, "rooms": r.rooms,
            "area": r.area, "floor": r.floor, "floors": r.floors, "description": r.description, "excl": r.is_exclusive,
            "pf": json.dumps(tags(r), ensure_ascii=False), "post_url": r.post_url, "pub": r.published_at,
            "reason": "not_actual" if status == "archived" else None, "arch": r.updated_at if status == "archived" else None,
            "created": r.created_at, "updated": r.updated_at}).scalar()
        files = [("photo", k) for k in (r.photos or [])] + ([("video", r.video)] if r.video else [])
        for pos, (kind, key) in enumerate(files):
            conn.execute(sa.text("INSERT INTO property_media (property_id, kind, path, position) VALUES (:p, :k, :path, :pos)"),
                         {"p": pid, "k": kind, "path": key, "pos": pos})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM properties WHERE post_fields ? 'offer_ident'"))  # media go with them (cascade)
    op.drop_column("properties", "site_hidden")
