"""CRM side of the site's own objects: sale objects (sale_objects) and cars (cars). Public side: services/site_feed.py.

An agent adds and edits them by hand; photos / video are keys in the row (offers/<s|c><id>/<uuid>.<ext>)."""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.api.deps import paginate
from app.models import Car, SaleObject, User, at_least
from app.services import properties as P
from app.services import site_feed
from app.services.common import get_or_404, log_event
from app.services.errors import DomainError

MODELS = {"sale": SaleObject, "car": Car}
MAX_PHOTOS, MAX_VIDEOS = P.MAX_MEDIA["photo"], P.MAX_MEDIA["video"]
# what the agent's form may write; status / photos / video / site_id / published_at only through the calls below
FIELDS = {
    "sale": ("service", "kind", "title", "headline", "district", "metro", "lat", "lng", "approx", "price", "currency", "rooms",
             "area", "floor", "floors", "building", "condition", "heating", "completion", "amenities", "description",
             "is_exclusive", "post_url"),
    "car": ("deal", "title", "period", "deposit", "year", "gearbox", "fuel", "body", "seats", "mileage", "pickup", "lat", "lng",
            "price", "currency", "description", "is_exclusive", "post_url"),
}


def kind_of(model) -> str:
    return "sale" if model is SaleObject else "car"


def out(o) -> dict:
    d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
    return {**d, "item_id": site_feed.ident_of(o), "public": o.status == "published" and bool(o.photos)}


def listing(db: Session, model, status: str | None, q: str | None, limit: int, offset: int) -> dict:
    stmt = select(model).order_by(model.id.desc())
    if status:
        stmt = stmt.where(model.status == status)
    if q:
        stmt = stmt.where(model.title.ilike(f"%{q.strip()}%"))
    return paginate(db, stmt, out, limit, offset)


def _changed(db: Session, o, actor: User | None, action: str, **data):
    log_event(db, kind_of(type(o)) + "_offer", o.id, action, actor, **data)
    db.commit()
    site_feed.clear_cache()  # the site shows the edit at once, not after the 60 s


def create(db: Session, model, data: dict, actor: User) -> object:
    allowed = FIELDS[kind_of(model)]
    o = model(**{k: v for k, v in data.items() if k in allowed}, agent_id=actor.id, status="draft")
    if (aid := data.get("agent_id")) and at_least(actor, "operator"):
        o.agent_id = aid
    db.add(o)
    db.flush()
    _changed(db, o, actor, "created")
    return o


def update(db: Session, model, oid: int, data: dict, actor: User) -> object:
    o = get_or_404(db, model, oid, "object", lock=True)
    for k, v in data.items():
        if k in FIELDS[kind_of(model)] or (k == "agent_id" and at_least(actor, "operator")):
            setattr(o, k, v)
    _changed(db, o, actor, "updated", fields=sorted(data))
    return o


def set_status(db: Session, model, oid: int, status: str, actor: User) -> object:
    o = get_or_404(db, model, oid, "object", lock=True)
    if status == "published" and not o.photos:
        raise DomainError("no_media", "Добавьте хотя бы одно фото перед публикацией")
    if status == "published" and not o.published_at:
        o.published_at = datetime.now(timezone.utc)
    o.status = status
    _changed(db, o, actor, status)
    return o


def upload(db: Session, model, oid: int, files: list[tuple[str, bytes]], actor: User) -> tuple[object, list[str]]:
    o = get_or_404(db, model, oid, "object", lock=True)
    photos, n_video = list(o.photos), 1 if o.video else 0
    for name, content in files:  # check everything first: a rejected batch stores nothing
        ext = os.path.splitext(name or "")[1].lower() or ".jpg"
        if ext not in P.PHOTO_EXT | P.VIDEO_EXT:
            raise DomainError("bad_file", f"Можно загружать только фото и видео: {name}")
        if len(content) > P.MAX_UPLOAD:
            raise DomainError("too_large", f"Файл слишком большой: {name}")
        if ext in P.VIDEO_EXT:
            n_video += 1
        else:
            photos.append(name)
        if n_video > MAX_VIDEOS or len(photos) > MAX_PHOTOS:
            raise DomainError("media_limit", f"Максимум {MAX_PHOTOS} фото и {MAX_VIDEOS} видео. Удалите лишнее, чтобы добавить новое", 422)
    keys, photos = [], list(o.photos)
    for name, content in files:
        ext = os.path.splitext(name or "")[1].lower() or ".jpg"
        key = f"offers/{site_feed.ident_of(o)}/{uuid.uuid4().hex}{ext}"
        storage.put(key, content)
        storage.put_preview(key, content)
        if ext in P.VIDEO_EXT:
            o.video = key
        else:
            photos.append(key)
        keys.append(key)
    o.photos = photos
    _changed(db, o, actor, "media_added", files=len(files))
    return o, keys


def reorder(db: Session, model, oid: int, keys: list[str], actor: User) -> object:
    o = get_or_404(db, model, oid, "object", lock=True)
    if sorted(keys or []) != sorted(o.photos):
        raise DomainError("bad_order", "Порядок фото устарел — обновите страницу", 409)
    o.photos = list(keys)
    _changed(db, o, actor, "media_reordered")
    return o


def delete_file(db: Session, model, oid: int, key: str, actor: User) -> object:
    o = get_or_404(db, model, oid, "object", lock=True)
    if key == o.video:
        o.video = None
    elif key in o.photos:
        o.photos = [k for k in o.photos if k != key]
    else:
        raise DomainError("not_found", "media not found")
    try:
        storage.delete(key)
    except Exception:
        pass  # a stray file in the bucket is harmless; the row is the truth
    _changed(db, o, actor, "media_deleted", key=key)
    return o
