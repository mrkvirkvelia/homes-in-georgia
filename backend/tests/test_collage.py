"""Irakli 11-22: the post's album opens with a 3×3 collage of its first 9 photos (notify.with_collage)."""
from PIL import Image

from app.telegram.notify import with_collage  # bound before conftest stubs notify.*


def _photos(tmp_path, n):
    out = []
    for i in range(n):
        p = tmp_path / f"{i}.jpg"
        Image.new("RGB", (800, 600 if i % 2 else 1000), (i * 20, 100, 150)).save(p)
        out.append(("photo", str(p)))
    return out


def test_collage_first_then_the_nine_photos(tmp_path):
    media = _photos(tmp_path, 12)
    out = with_collage(media, str(tmp_path))
    assert len(out) == 10 and out[0][1].endswith("collage.jpg") and out[1:] == media[:9]
    with Image.open(out[0][1]) as im:
        assert im.size == (3 * 427 + 8, 3 * 320 + 8)
        assert min(im.getpixel((427 + 2, 10))) > 240  # the white gap between the tiles (JPEG: near white)


def test_with_a_video_the_album_keeps_it(tmp_path):
    media = _photos(tmp_path, 9) + [("video", str(tmp_path / "v.mp4"))]
    out = with_collage(media, str(tmp_path))
    assert len(out) == 10 and out[0][1].endswith("collage.jpg") and out[1:9] == media[:8] and out[-1][0] == "video"


def test_fewer_than_nine_photos_no_collage(tmp_path):
    media = _photos(tmp_path, 6)
    assert with_collage(media, str(tmp_path)) == media
