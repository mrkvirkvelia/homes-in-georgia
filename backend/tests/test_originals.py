"""«Скачать оригиналы» (Stanislav 11-22): the object's photos as uploaded, in the gallery order, one zip; private files
(passport, extract) never in it; an agent who can't open the card gets a 404."""
import io
import zipfile

from app import storage
from app.models import PropertyMedia
from tests.conftest import auth, make_user
from tests.test_similar import _object


def test_originals_zip(db, client):
    vika, ana = make_user(db, "agent", "Вика"), make_user(db, "agent", "Аня")
    pid = _object(db, client, vika)
    for pos, (key, data) in enumerate([(f"properties/{pid}/b.jpg", b"second"), (f"properties/{pid}/a.JPG", b"first"),
                                       (f"private/properties/{pid}/passport.jpg", b"secret")]):
        storage.put(key, data)
        db.add(PropertyMedia(property_id=pid, kind="photo", path=key, position=[1, 0, 2][pos], dhash=0))
    db.commit()
    r = client.get(f"/api/properties/{pid}/originals", headers=auth(vika))
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == [f"{pid}_01.jpg", f"{pid}_02.jpg"]
    assert [z.read(n) for n in z.namelist()] == [b"first", b"second"]
    assert client.get(f"/api/properties/{pid}/originals", headers=auth(ana)).status_code == 404
