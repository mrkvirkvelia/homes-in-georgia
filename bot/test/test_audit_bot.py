"""Audit fixes in the client bot: pets ban in the hard filter, row-locked state updates, shown only once delivered,
superseded searches don't write the state, CRM photos in the visual index, re-indexing changed ads."""
import asyncio
import os
os.environ["ENV_FILE"] = os.devnull
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import pg  # noqa: F401
import core
import db
from test_core import Base, item


class HardFilterPets(unittest.TestCase):
    def test_pets_ban_from_column_or_details(self):
        pool = [{"id": "a", "pets": "нет"}, {"id": "b", "details": {"pets": "not_allowed"}},
                {"id": "c", "pets": "да", "details": {"pets": "allowed"}}, {"id": "d"}]
        self.assertEqual([i["id"] for i in core.hard_filter(pool, {"pets": True})], ["c", "d"])
        self.assertEqual(len(core.hard_filter(pool, {"pets": None})), 4)


class Audit(Base):
    def setUp(self):
        super().setUp()
        self.sync([item("ss1"), item("ss2", price_usd=900), item("ss3")])
        self.publish_objects("ss1", "ss2", "ss3")
        self.cl = core.client("tg", 42, username="anna", name="Anna", lang_hint="ru")

    def pid(self, lid):
        return int(self.o(lid)[3:])

    # 2: the channel post's button -> one lead per client and object, also for a manually created object
    def post_start(self, pid):
        import journey
        sent = []

        async def send_message(chat_id, text, **kw):
            sent.append(text)
        upd = SimpleNamespace(effective_chat=SimpleNamespace(id=42))
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=send_message))
        with mock.patch.object(journey.notify, "knows_operator", lambda cid: True):
            return asyncio.run(journey.on_post_start(upd, ctx, self.cl, pid)), sent

    def leads(self):
        with db.tx() as c:
            return [tuple(r) for r in c.execute("SELECT listing_id, property_id FROM leads WHERE client_id = ? ORDER BY id",
                                                (self.cl["id"],))]

    def test_post_start_manual_object(self):
        with db.tx() as c:  # created in the CRM by hand: no source ad
            c.execute("UPDATE properties SET listing_id = NULL WHERE id = ?", (self.pid("ss1"),))
        ok, sent = self.post_start(self.pid("ss1"))
        self.assertTrue(ok)
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.leads(), [(self.o("ss1"), self.pid("ss1"))])

    def test_post_start_and_search_like_share_the_lead(self):
        from app.db import SessionLocal
        from app.services import leads
        with SessionLocal() as s:
            leads.create_from_like(s, self.cl["id"], self.o("ss2"))  # ❤️ on the card in the search
        self.assertTrue(self.post_start(self.pid("ss2"))[0])
        self.assertEqual(self.leads(), [(self.o("ss2"), self.pid("ss2"))])
        with db.tx() as c:
            c.execute("UPDATE properties SET status = 'archived' WHERE id = ?", (self.pid("ss3"),))
        self.assertFalse(self.post_start(self.pid("ss3"))[0])  # gone: the caller shows similar ones

    # 3: concurrent read-modify-write of clients.state
    def test_update_holds_a_row_lock(self):
        def slow(st, r):
            st["msgs"].append("a")
            time.sleep(0.4)
        a = threading.Thread(target=core.update, args=(dict(self.cl), slow))
        a.start()
        time.sleep(0.1)
        core.update(dict(self.cl), lambda st, r: st["msgs"].append("b"))  # waits for a's commit, reads its write
        a.join()
        self.assertEqual(core.client("tg", 42)["state"]["msgs"], ["a", "b"])

    # 4: shown only once delivered; a superseded search keeps out of the state
    def test_search_steps_dont_mark_shown(self):
        self.pick = ["ss1", "ss2"]
        core.add_input(self.cl, text="2 спальни")
        core.begin_search(self.cl)
        res = [b for b in core.search_steps(self.cl)]
        self.assertEqual(self.ids(res[0]), ["ss1", "ss2"])
        self.assertEqual(core.client("tg", 42)["state"]["shown"], [])  # nothing reached the client yet
        self.assertEqual(core.search(core.client("tg", 42))["items"][0]["listing"]["id"], self.o("ss1"))  # still offered

    def test_send_cards_marks_each_delivered_card(self):
        import bot
        self.pick = ["ss1", "ss2"]
        core.add_input(self.cl, text="2 спальни")
        core.begin_search(self.cl)
        res = next(core.search_steps(self.cl))
        mid = []

        async def send_message(chat_id, text, **kw):
            if self.o("ss2") in str(kw.get("reply_markup")):
                raise RuntimeError("Telegram refused the card")
            mid.append(len(mid) + 1)
            return SimpleNamespace(message_id=mid[-1])

        async def run():
            fake = SimpleNamespace(send_message=send_message)
            with mock.patch.object(bot, "send_album", mock.AsyncMock()):
                return [i["id"] async for i in bot.send_cards(fake, 42, self.cl, res["items"], res["search_id"])]
        asyncio.run(run())
        self.assertEqual(core.client("tg", 42)["state"]["shown"], [self.o("ss1")])  # ss2 never arrived: offered again
        with db.tx() as c:
            self.assertEqual([r[0] for r in c.execute("SELECT listing_id FROM client_views")], [self.o("ss1")])

    def test_superseded_search_writes_no_state(self):
        old = dict(self.cl)
        core.begin_search(old)
        core.add_input(self.cl, text="новый запрос")  # the request changed while the old search ran
        before = core.client("tg", 42)["state"]
        out = core._finish(old, [], "u", 0, 3, near=["old", None])
        self.assertIsNotNone(out["search_id"])  # the search still counts
        self.assertEqual(core.client("tg", 42)["state"], before)
        cur = core.client("tg", 42)
        core.begin_search(cur)
        core._finish(cur, [], "u", 0, 3, near=["new", None])
        self.assertEqual(core.client("tg", 42)["state"]["near"], ["new", None])
        core.reset(cur)  # /start also moves the generation on
        core._finish(cur, [], "u", 0, 3, near=["late", None])
        self.assertIsNone(core.client("tg", 42)["state"]["near"])


if __name__ == "__main__":
    unittest.main()
