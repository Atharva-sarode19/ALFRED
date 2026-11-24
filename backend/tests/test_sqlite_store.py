import tempfile
import unittest
from pathlib import Path

from app.database.sqlite_store import SQLiteStore, tokenize


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SQLiteStore(Path(self._tmp.name) / "alfred.db")


class NotesTests(StoreTestCase):
    def test_create_get_search_delete(self):
        note = self.store.create_note("Groceries", "milk, eggs and bread")
        self.assertEqual(self.store.get_note(note["id"])["content"], "milk, eggs and bread")
        self.assertEqual(len(self.store.search_notes("EGGS bread")), 1)
        self.assertEqual(self.store.search_notes("laptop"), [])
        self.assertTrue(self.store.delete_note(note["id"]))
        self.assertFalse(self.store.delete_note(note["id"]))
        self.assertIsNone(self.store.get_note(note["id"]))

    def test_like_wildcards_are_escaped(self):
        # "_" is a word character, so it reaches the LIKE pattern and must not act as a wildcard.
        self.store.create_note("Code", "use snake_case names")
        self.store.create_note("Other", "snakeXcase is different")
        self.assertEqual([n["title"] for n in self.store.search_notes("snake_case")], ["Code"])

    def test_blank_query_lists_recent(self):
        self.store.create_note("a", "1")
        self.store.create_note("b", "2")
        self.assertEqual([n["title"] for n in self.store.search_notes(None)], ["b", "a"])


class ReminderTests(StoreTestCase):
    def test_scopes_and_ordering(self):
        self.store.create_reminder("past", "2026-01-01T09:00:00+00:00", None)
        self.store.create_reminder("later", "2026-12-01T09:00:00+00:00", "bring ID")
        self.store.create_reminder("soon", "2026-11-05T09:00:00+00:00", None)
        now = "2026-11-02T00:00:00+00:00"
        self.assertEqual([r["title"] for r in self.store.list_reminders("upcoming", now)], ["soon", "later"])
        self.assertEqual([r["title"] for r in self.store.list_reminders("past", now)], ["past"])
        self.assertEqual(len(self.store.list_reminders("all", now)), 3)

    def test_delete(self):
        r = self.store.create_reminder("x", "2026-12-01T09:00:00+00:00", None)
        self.assertTrue(self.store.delete_reminder(r["id"]))
        self.assertFalse(self.store.delete_reminder(r["id"]))


class FileTests(StoreTestCase):
    def _add(self, fid, name, text, chunks):
        return self.store.add_file(fid, name, fid + ".txt", "text/plain", len(text), text, chunks)

    def test_search_by_content_and_name(self):
        self._add("a" * 32, "project_report.txt", "The architecture uses a message queue.",
                  ["The architecture uses a message queue."])
        self._add("b" * 32, "recipes.txt", "Pasta needs salt.", ["Pasta needs salt."])

        by_content = self.store.search_files("message queue architecture")
        self.assertEqual([r["name"] for r in by_content], ["project_report.txt"])
        self.assertTrue(by_content[0]["snippets"])

        by_name = self.store.search_files("find my project report")
        self.assertEqual(by_name[0]["name"], "project_report.txt")
        self.assertTrue(by_name[0]["name_match"])

        self.assertEqual(self.store.search_files("zebra"), [])

    def test_blank_query_lists_newest_first(self):
        self._add("a" * 32, "first.txt", "one", ["one"])
        self._add("b" * 32, "second.txt", "two", ["two"])
        self.assertEqual([r["name"] for r in self.store.search_files("")], ["second.txt", "first.txt"])

    def test_read_text_paging(self):
        text = "0123456789" * 10
        self._add("c" * 32, "digits.txt", text, [text])
        self.assertEqual(self.store.read_file_text("c" * 32, 0, 5), "01234")
        self.assertEqual(self.store.read_file_text("c" * 32, 95, 50), "56789")
        self.assertIsNone(self.store.read_file_text("missing", 0, 5))

    def test_search_within_one_file(self):
        self._add("d" * 32, "a.txt", "alpha", ["alpha text about cats", "beta text about dogs"])
        self._add("e" * 32, "b.txt", "beta", ["cats again"])
        hits = self.store.search_chunks_in_file("d" * 32, "cats")
        self.assertEqual([h["chunk_index"] for h in hits], [0])

    def test_fallback_search_without_fts(self):
        self.store._fts = False  # simulate SQLite built without FTS5
        self._add("f" * 32, "notes.txt", "kubernetes cluster", ["kubernetes cluster setup"])
        self.assertEqual(self.store.search_files("kubernetes")[0]["name"], "notes.txt")


class TokenizeTests(unittest.TestCase):
    def test_drops_stopwords_and_dedupes(self):
        self.assertEqual(tokenize("Find my project report project"), ["project", "report"])


if __name__ == "__main__":
    unittest.main()
