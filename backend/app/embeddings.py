"""Property vectors for similar-object search: properties.text_embedding / photo_embedding (pgvector, migration 0006).

The encoder is the bot's multilingual SigLIP (bot/embed.py), so property and catalog vectors share one space. It needs
torch + transformers (bot/requirements-embed.txt; not in deploy/Dockerfile yet); without them everything is a no-op.

CLI:  python -m app.embeddings backfill          # properties that have no text vector yet
      python -m app.embeddings backfill --all    # re-embed every property
      python -m app.embeddings photos            # per-photo vectors (photo_vectors), what the worker runs by itself

Per-photo vectors (migration 0034, «похожие фото (другой ракурс)» in services/similar.py): every photo of an object and
of a live outside ad. The worker starts `photos` in a child process when something is missing (worker.photo_vectors_tick):
the model (~1.5 GB) lives only in that child, which exits after PHOTO_MINUTES, so the worker itself stays small. Low
priority: nice 15, one torch thread, a pause after every small batch. Objects' photos first (an upload is embedded within
a minute; an exclusive is searched again then), then the ads: copied from the bot's vectors.npz (refresh.sh embed.py
already has them per photo) when its fingerprint is the ad's current one, else computed once the ad is NPZ_GRACE old.
Resumable: what is done is in the table (an ad: listings.photo_vec_sig), a killed run just starts over the rest.
"""
import hashlib
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import storage
from app.config import REPO_ROOT
from app.models import Property, PropertyMedia
from app.services.common import jload

DIM = 768


def encoder():
    """bot/embed.py, or None when torch/transformers are not installed."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return None
    if str(REPO_ROOT / "bot") not in sys.path:
        sys.path.append(str(REPO_ROOT / "bot"))
    import embed
    return embed


def property_text(p: Property) -> str:
    # SigLIP reads only ~64 tokens: the description first
    return " ".join(str(x) for x in (p.description, p.district, p.address) if x).strip()


def _vec(v):
    return None if v is None else "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"


def embed_property(db: Session, p: Property, enc=None) -> bool:
    """Computes and stores both vectors of one property (photo = normalized mean of its photos). False = no encoder."""
    import numpy as np
    enc = enc or encoder()
    if enc is None:
        return False
    t = property_text(p)
    tv = enc.encode_texts([t])[0] if t else None
    keys = db.scalars(select(PropertyMedia.path).where(PropertyMedia.property_id == p.id, PropertyMedia.kind == "photo")
                      .order_by(PropertyMedia.position)).all()
    with tempfile.TemporaryDirectory() as tmp:
        paths = [f for k in keys if (f := storage.fetch(k, tmp))]
        img = np.asarray(enc.encode_images(paths)) if paths else None
    pv = None
    if img is not None and len(img):
        m = img.mean(0)
        pv = m / max(float(np.linalg.norm(m)), 1e-9)
    db.execute(text("UPDATE properties SET text_embedding = CAST(:t AS vector), photo_embedding = CAST(:p AS vector) "
                    "WHERE id = :id"), {"t": _vec(tv), "p": _vec(pv), "id": p.id})
    db.commit()
    return True


def backfill(all_: bool = False) -> int:
    from app.db import SessionLocal
    enc = encoder()
    if enc is None:
        print("embeddings: torch/transformers are not installed (bot/requirements-embed.txt), nothing done")
        return 0
    with SessionLocal() as db:
        ids = db.scalars(text("SELECT id FROM properties" + ("" if all_ else " WHERE text_embedding IS NULL") +
                              " ORDER BY id")).all()
        for pid in ids:
            embed_property(db, db.get(Property, pid), enc)
    print(f"embeddings: {len(ids)} properties embedded")
    return len(ids)


# ---------------------------------------------------------------- per-photo vectors

LIVE_AD = "status IN ('published', 'pending_review', 'copy') AND source NOT IN ('object', 'agency')"  # similar.LIVE, its _ads()
PHOTO_MINUTES, BATCH, PAUSE = 10, 8, 2.0  # one child run; photos per model call; seconds of rest after each call
NPZ_GRACE = timedelta(hours=2)  # a new ad: refresh.sh embeds it right after the sync, wait for that before computing it


def _bot_embed():
    if str(REPO_ROOT / "bot") not in sys.path:
        sys.path.append(str(REPO_ROOT / "bot"))
    import embed
    return embed


def npz_path():
    """The bot's vectors.npz (refresh runs `embed.py` in bot/, DATA_DIR relative to it)."""
    return os.environ.get("EMB_PATH") or str(REPO_ROOT / "bot" / os.environ.get("DATA_DIR", "data") / "vectors.npz")


def _rows(vs) -> list:
    """Encoder rows -> vector literals, None for an unreadable photo (the encoder's zero row)."""
    import numpy as np
    return [_vec(v) if np.any(v) else None for v in vs]


def media_pending(db: Session, limit: int) -> list:
    return db.execute(text("SELECT m.id, m.path, m.property_id FROM property_media m WHERE m.kind = 'photo' AND NOT EXISTS "
                           "(SELECT 1 FROM photo_vectors v WHERE v.media_id = m.id) ORDER BY m.id DESC LIMIT :n"),
                      {"n": limit}).all()


def ads_pending(db: Session, older_than: str | None = None, limit: int | None = None) -> list:
    """Live ads whose rows are missing or were made from other photos: (id, photos, the fingerprint's fields...)."""
    q = (f"SELECT id, photos, looks, style, renovation, light, furniture, features FROM listings WHERE {LIVE_AD} "
         "AND photos <> '[]' AND photo_vec_sig IS DISTINCT FROM md5(photos)"
         + (" AND first_seen < :t" if older_than else "") + " ORDER BY first_seen DESC" + (" LIMIT :n" if limit else ""))
    return db.execute(text(q), {"t": older_than, "n": limit}).all()


def _put_ad(db: Session, lid: str, photos: str, vecs: list) -> None:
    db.execute(text("DELETE FROM photo_vectors WHERE listing_id = :l"), {"l": lid})
    if vecs:
        db.execute(text("INSERT INTO photo_vectors (listing_id, n, vec) VALUES (:l, :n, CAST(:v AS vector))"),
                   [{"l": lid, "n": n, "v": v} for n, v in enumerate(vecs)])
    db.execute(text("UPDATE listings SET photo_vec_sig = :s WHERE id = :l"),
               {"s": hashlib.md5(photos.encode()).hexdigest(), "l": lid})


def import_npz(db: Session, deadline: float = float("inf")) -> int:
    """Ads the bot's vectors.npz already has per photo, for their current photos (the same fingerprint, one row per
    photo): copied, nothing computed. -> ads copied."""
    import numpy as np
    p = npz_path()
    if not os.path.exists(p):
        return 0
    todo = ads_pending(db)
    if not todo:
        return 0
    fp = _bot_embed().fingerprint
    with np.load(p) as z:
        at = {str(x): n for n, x in enumerate(z["ids"])}
        keys, owner = z["keys"], z["owner"]
        hit = []
        for r in todo:
            n = at.get(r.id)
            photos = jload(r.photos, []) or []
            i = {"photos": photos, "features": jload(r.features, []) or [], "looks": r.looks, "style": r.style,
                 "renovation": r.renovation, "light": r.light, "furniture": r.furniture}
            if n is None or str(keys[n]) != fp(i):
                continue
            a, b = np.searchsorted(owner, n, "left"), np.searchsorted(owner, n, "right")  # owner is sorted
            if b - a == len(photos):  # every photo was there when the bot embedded it: row k is photos[k]
                hit.append((r, a, b))
        if not hit:
            return 0
        photo = z["photo"]  # the big array (~3 KB a photo), read only when something is copied from it
    done = 0
    for r, a, b in hit:
        _put_ad(db, r.id, r.photos, _rows(photo[a:b]))
        done += 1
        if done % 200 == 0:
            db.commit()
            if time.time() > deadline:
                break
    db.commit()
    return done


def _ad_file(ref: str, tmp: str) -> str | None:
    """An ad's photo ref -> a local file: bot/raw/img/... (relative to bot/), a CRM s3:<key>; remote http ones: None."""
    if ref.startswith("s3:"):
        return storage.fetch(ref[3:], tmp)
    if ref.startswith(("http://", "https://")):
        return None
    f = ref if os.path.isabs(ref) else str(REPO_ROOT / "bot" / ref)
    return f if os.path.isfile(f) else None


def _encode(enc, files: list) -> list:
    """Encoder over the readable files, None in the place of a missing one."""
    have = [f for f in files if f]
    vs = iter(_rows(enc.encode_images(have)) if have else [])
    return [next(vs) if f else None for f in files]


def embed_media(db: Session, enc, limit: int = BATCH) -> set[int]:
    """The newest object photos without a row -> rows; the objects touched."""
    rows = media_pending(db, limit)
    if not rows:
        return set()
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for mid, path, _ in rows:  # the ~640 px preview decodes faster; the model sees 256 px anyway
            data = storage.read(storage.preview_key(path)) or storage.read(path)
            f = os.path.join(tmp, f"{mid}.img") if data else None
            if f:
                with open(f, "wb") as fh:
                    fh.write(data)
            files.append(f)
        vecs = _encode(enc, files)
    db.execute(text("INSERT INTO photo_vectors (media_id, vec) VALUES (:m, CAST(:v AS vector)) ON CONFLICT (media_id) DO NOTHING"),
               [{"m": mid, "v": v} for (mid, _, _), v in zip(rows, vecs)])
    db.commit()
    return {pid for _, _, pid in rows}


def embed_ad(db: Session, enc, row) -> None:
    photos = jload(row.photos, []) or []
    with tempfile.TemporaryDirectory() as tmp:
        vecs = _encode(enc, [_ad_file(str(r), tmp) for r in photos])
    _put_ad(db, row.id, row.photos, vecs)
    db.commit()


def _rescan(db: Session, pids: set[int]) -> None:
    """An exclusive's photos got their vectors: its duplicate search runs again with them (the upload's own search ran
    before they existed)."""
    from app.services import properties as P
    for p in db.scalars(select(Property).where(Property.id.in_(pids), Property.is_exclusive.is_(True),
                                               Property.status != "archived")):
        P.schedule_dup_scan(db, p, "photo_vectors")
    db.commit()


def run_photos(minutes: float = PHOTO_MINUTES, enc=None, pause: float = PAUSE) -> dict:
    """One resumable pass (the worker's child): npz copies, then object photos, then ads, until done or the time is up."""
    from app.db import SessionLocal
    deadline = time.time() + minutes * 60
    st = {"npz": 0, "media": 0, "ads": 0}
    with SessionLocal() as db:
        st["npz"] = import_npz(db, deadline)
        while time.time() < deadline:
            if media_pending(db, 1):
                enc = enc or encoder()
                if enc is None:
                    break
                pids = embed_media(db, enc)
                st["media"] += 1
                _rescan(db, pids)
            else:
                old = (datetime.now(timezone.utc) - NPZ_GRACE).isoformat(timespec="seconds")
                rows = ads_pending(db, old, limit=1)
                if not rows:
                    break
                enc = enc or encoder()
                if enc is None:
                    break
                embed_ad(db, enc, rows[0])
                st["ads"] += 1
            time.sleep(pause)
    return st


def photos_due(db: Session) -> bool:
    """Something for run_photos to compute (the npz copy is checked by the worker on the file's change)."""
    old = (datetime.now(timezone.utc) - NPZ_GRACE).isoformat(timespec="seconds")
    return bool(media_pending(db, 1) or ads_pending(db, old, limit=1))


def _photos_main():
    os.nice(15)
    try:
        import torch
        torch.set_num_threads(int(os.environ.get("PHOTO_VECTORS_THREADS", "1")))
    except ImportError:
        pass
    print(f"photo vectors: {run_photos()}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["photos"]:
        _photos_main()
    elif sys.argv[1:2] == ["backfill"]:
        backfill(all_="--all" in sys.argv)
    else:
        sys.exit(__doc__)
