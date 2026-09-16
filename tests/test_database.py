import os
import tempfile
import unittest
from unittest.mock import patch

import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.patch = patch.object(database, "DB_PATH", self.db_path)
        self.patch.start()
        database.init_db()

    def tearDown(self):
        self.patch.stop()
        self.temp_dir.cleanup()

    def test_note_is_scoped_to_owner(self):
        note_id = database.add_note(1, "deneme")
        self.assertEqual([row["content"] for row in database.get_notes(1)], ["deneme"])
        self.assertFalse(database.delete_note(note_id, 2))
        self.assertTrue(database.delete_note(note_id, 1))

    def test_task_lifecycle_and_owner_check(self):
        task_id = database.add_task(1, "testleri çalıştır")
        self.assertFalse(database.complete_task(task_id, 2))
        self.assertTrue(database.complete_task(task_id, 1))
        self.assertEqual(database.get_tasks(1)[0]["is_done"], 1)
        self.assertTrue(database.delete_task(task_id, 1))


if __name__ == "__main__":
    unittest.main()
