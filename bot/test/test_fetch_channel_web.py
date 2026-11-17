"""Competitor history walk on t.me/s (fetch_channel_web.py): a slice per tick under FETCH_BACKFILL_SEC, resumed from the
cursor file, the source marked backfilled only once the walk ends; its status lands in sources.options. No network:
a fake channel of posts 10..1, two posts a page."""
import json
import os
os.environ["ENV_FILE"] = os.devnull
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import pg
import db
import fetch_channel_web as fcw


def page_ids(url):
    before = int(url.split("before=")[1]) if "before=" in url else 11
    return [i for i in range(before - 2, before) if i > 0]  # a t.me/s page lists oldest first


class Walk(unittest.TestCase):
    def setUp(self):
        fake_get = lambda c, url: type("R", (), {"text": url})
        fake_parse = lambda url: [{"id": i, "date": None, "text": "t", "links": [], "photos": [(i, "u")], "videos": []}
                                  for i in page_ids(url)]
        for p in (mock.patch.object(fcw, "get", fake_get), mock.patch.object(fcw, "parse", fake_parse),
                  mock.patch.object(fcw, "download", lambda c, url, path: True), mock.patch.object(fcw, "PAUSE", 0)):
            p.start()
            self.addCleanup(p.stop)

    def test_deadline_returns_cursor_and_resume_continues(self):
        items, cur = fcw.fetch(None, "x", "competitor", 100, 1, 1000, deadline=time.time() - 1)
        self.assertEqual(([i["id"] for i in items], cur), ([10, 9], {"before": 9, "newest": 10}))
        items, cur = fcw.fetch(None, "x", "competitor", 100, 1, 1000, start=cur)
        self.assertEqual(([i["id"] for i in items], cur), ([8, 7, 6, 5, 4, 3, 2, 1], None))
        # scan counts from the walk's first (newest) post, not from where a slice resumed
        items, _ = fcw.fetch(None, "x", "competitor", 100, 1, 5, start={"before": 9, "newest": 10})
        self.assertEqual([i["id"] for i in items], [8, 7, 6, 5])

    def test_main_slices_resumes_and_marks_backfilled(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        Path(tmp.name, "sources.json").write_text(json.dumps({
            "telegram_defaults": {"want": 40, "photos": 1, "scan": 200},
            "telegram_channels": [{"username": "rival", "kind": "competitor", "competitor": True,
                                   "backfill": {"want": 500, "scan": 10000}}]}))
        reports = []
        raw = Path(tmp.name, "raw")
        with mock.patch.object(fcw, "ROOT", tmp.name), mock.patch.object(fcw, "report", lambda u, **st: reports.append(st)):
            with mock.patch.object(fcw, "BACKFILL_SEC", -1):  # out of time after the first page
                self.assertEqual(fcw.main(), 0)
            self.assertEqual(json.loads((raw / "backfill_rival.cursor").read_text()), {"before": 9, "newest": 10, "found": 2})
            self.assertFalse((raw / "backfill_rival.done").exists())
            self.assertEqual([i["id"] for i in json.loads((raw / "channel_rival.json").read_text())], [10, 9])
            self.assertEqual(reports[-1], {"last_error": None, "last_posts": 2, "last_note": "история загружается, постов: 2"})

            self.assertEqual(fcw.main(), 0)  # next tick: resumes, walks to the end
            self.assertTrue((raw / "backfill_rival.done").exists())
            self.assertFalse((raw / "backfill_rival.cursor").exists())
            self.assertEqual([i["id"] for i in json.loads((raw / "channel_rival.json").read_text())], list(range(10, 0, -1)))
            self.assertEqual(reports[-1], {"last_error": None, "last_posts": 10, "last_note": "история загружена, постов: 10"})

            with mock.patch.object(fcw, "get", mock.Mock(side_effect=RuntimeError("t.me down"))):
                self.assertEqual(fcw.main(), 1)
            self.assertEqual(reports[-1], {"last_error": "t.me down"})


class Status(unittest.TestCase):
    def test_source_status_in_options_not_in_sources_json(self):
        pg.reset()
        with db.tx() as c:
            c.execute("INSERT INTO sources (kind, key, name, options) VALUES ('tg_competitor', 'rival', 'Rival', ?)",
                      (json.dumps({"competitor": True}),))
        db.source_status("rival", last_error="boom", last_note=None)
        with db.tx() as c:
            o = json.loads(c.execute("SELECT options FROM sources WHERE key = 'rival'").fetchone()["options"])
            ch = db.sources_config(c)["telegram_channels"][0]
        self.assertEqual((o["competitor"], o["last_error"], bool(o["last_run"])), (True, "boom", True))
        self.assertFalse(set(db.STATUS) & set(ch))


if __name__ == "__main__":
    unittest.main()
