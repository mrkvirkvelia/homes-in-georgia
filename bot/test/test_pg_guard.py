"""test/pg.py drops and rebuilds its schema: it refuses a database or schema that is not clearly a test one."""
import unittest

import pg


class PgGuardTest(unittest.TestCase):
    def test_test_databases_pass(self):
        pg.check_test_db("postgresql+psycopg://homes:homes@homes-ci-db:5432/homes_test", None, "bot_test")  # autodeploy.sh
        pg.check_test_db("postgresql://postgres@/homes_test?host=/tmp/pg", "postgresql://postgres@/homes?host=/tmp/pg", "bot_test")

    def test_refuses_non_test_database_schema_or_the_app_database(self):
        for test_url, main_url, schema in (
                ("postgresql+psycopg://homes:homes@db:5432/homes", None, "bot_test"),
                ("postgresql+psycopg://homes:homes@db:5432/homes_test", None, "public"),
                ("postgresql+psycopg://homes:homes@db/homes_test", "postgresql://u:p@db:5432/homes_test", "bot_test")):
            with self.subTest(test_url=test_url, schema=schema), self.assertRaises(RuntimeError):
                pg.check_test_db(test_url, main_url, schema)


if __name__ == "__main__":
    unittest.main()
