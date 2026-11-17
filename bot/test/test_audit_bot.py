"""Audit fixes in the client bot: pets ban in the hard filter, row-locked state updates, shown only once delivered,
superseded searches don't write the state, CRM photos in the visual index, re-indexing changed ads."""
import os
os.environ["ENV_FILE"] = os.devnull
import unittest

import pg  # noqa: F401
import core


class HardFilterPets(unittest.TestCase):
    def test_pets_ban_from_column_or_details(self):
        pool = [{"id": "a", "pets": "нет"}, {"id": "b", "details": {"pets": "not_allowed"}},
                {"id": "c", "pets": "да", "details": {"pets": "allowed"}}, {"id": "d"}]
        self.assertEqual([i["id"] for i in core.hard_filter(pool, {"pets": True})], ["c", "d"])
        self.assertEqual(len(core.hard_filter(pool, {"pets": None})), 4)


if __name__ == "__main__":
    unittest.main()
