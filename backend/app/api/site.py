"""Public read-only API for the site hge.ge (no login; same origin behind Caddy). Logic: services/site_feed.py."""
import mimetypes

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import storage
from app.db import get_db
from app.services import site_feed
from app.services.errors import DomainError

public = APIRouter(prefix="/public/site", tags=["site"])
CACHE = {"Cache-Control": "public, max-age=60"}
PHOTO_CACHE = {"Cache-Control": "public, max-age=86400"}


def _file(key: str, preview: bool = False):
    """The stored file: s3 -> preview from the local cache or a redirect; local -> the file (preview made on demand)."""
    if storage.is_s3():
        if preview and (f := storage.cached(storage.preview_key(key))):
            return FileResponse(f, media_type="image/webp", headers=PHOTO_CACHE)
        return RedirectResponse(storage.url(key), status_code=307, headers=PHOTO_CACHE)
    f = storage.local_path(key)
    if not f.is_file():
        raise DomainError("not_found", "file missing")
    f = (storage.local_preview(f, key) if preview else None) or f
    return FileResponse(f, media_type=mimetypes.guess_type(f.name)[0] or "image/jpeg", headers=PHOTO_CACHE)


@public.get("/listings")
def listings(response: Response, db: Session = Depends(get_db, scope="function")):
    response.headers.update(CACHE)
    return site_feed.cached_feed(db)


@public.get("/listings/{ident}")
def listing(ident: str, response: Response, db: Session = Depends(get_db, scope="function")):
    if (d := site_feed.detail(db, ident)) is None:
        raise DomainError("not_found", "listing not found")
    response.headers.update(CACHE)
    return d


@public.get("/photos/{ident}/{n}")
def photo(ident: str, n: int, preview: bool = Query(False, alias="p"), db: Session = Depends(get_db, scope="function")):
    o = site_feed.find(db, ident)
    keys = site_feed.keys(db, o) if o else []
    if not 0 <= n < len(keys):
        raise DomainError("not_found", "photo not found")
    return _file(keys[n], preview)


@public.get("/video/{ident}")
def video(ident: str, db: Session = Depends(get_db, scope="function")):
    o = site_feed.find(db, ident)
    if not o or not (key := site_feed.video_key(db, o)):
        raise DomainError("not_found", "video not found")
    return _file(key)
