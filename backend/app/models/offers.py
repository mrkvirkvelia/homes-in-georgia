"""What the site hge.ge shows besides rent: sale objects (resale, new buildings, commercial for sale) and cars.

Rent (apartments, daily, commercial for rent) stays in `properties`. Here an agent types the facts by hand (no funnel,
no owner): draft -> published (needs a photo) -> archived. Photos / video are storage keys in the row itself; the
words (building, condition, heating, metro, amenities) are the site's own (services/site_feed.py)."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr

from app.db import Base

OFFER_STATUSES = ("draft", "published", "archived")
SALE_SERVICES = ("sale", "new", "commercial")  # resale | new buildings | commercial for sale
SALE_KINDS = ("apartment", "house", "land", "commercial")
CAR_DEALS = ("rent", "sale")


class _Offer:
    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)  # the address (sale) / the model (car)
    description = Column(Text)
    price = Column(Numeric(14, 2))
    currency = Column(Text, nullable=False, server_default="USD")
    lat = Column(Float)
    lng = Column(Float)
    is_exclusive = Column(Boolean, nullable=False, server_default=text("false"))
    photos = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))  # storage keys, in show order (max 9)
    video = Column(Text)  # storage key
    post_url = Column(Text)  # the Telegram post, if any
    site_id = Column(Text, unique=True)  # the old site's id ("homes-3123"): old links resolve to it
    status = Column(Text, nullable=False, server_default="draft")
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @declared_attr
    def agent_id(cls):
        return Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))


class SaleObject(_Offer, Base):
    __tablename__ = "sale_objects"
    __table_args__ = (Index("sale_objects_status_idx", "status"),
                      CheckConstraint(f"status IN {OFFER_STATUSES}", name="sale_objects_status_check"),
                      CheckConstraint(f"service IN {SALE_SERVICES}", name="sale_objects_service_check"))
    service = Column(Text, nullable=False)
    kind = Column(Text, nullable=False, server_default="apartment")
    headline = Column(Text)
    district = Column(Text)
    metro = Column(Text)
    approx = Column(Boolean, nullable=False, server_default=text("false"))  # the point is approximate: the site shows no exact pin
    rooms = Column(Integer)
    area = Column(Numeric(10, 2))
    floor = Column(Integer)
    floors = Column(Integer)
    building = Column(Text)  # new | old | historical
    condition = Column(Text)  # white_frame | green_frame | black_frame | renovated | mixed | old
    heating = Column(Text)  # central | gas | electric
    completion = Column(Text)  # new buildings: "Q4 2027"
    amenities = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))


class Car(_Offer, Base):
    __tablename__ = "cars"
    __table_args__ = (Index("cars_status_idx", "status"),
                      CheckConstraint(f"status IN {OFFER_STATUSES}", name="cars_status_check"),
                      CheckConstraint(f"deal IN {CAR_DEALS}", name="cars_deal_check"))
    deal = Column(Text, nullable=False)  # rent | sale
    period = Column(Text)  # rent: day | month
    deposit = Column(Numeric(12, 2))
    year = Column(Integer)
    gearbox = Column(Text)  # auto | manual
    fuel = Column(Text)
    body = Column(Text)
    seats = Column(Integer)
    mileage = Column(Integer)
    pickup = Column(Text)  # rent: where the car is handed over
