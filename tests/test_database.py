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

    def test_reminder_is_persisted_and_marked_sent(self):
        from datetime import datetime, timedelta, timezone

        reminder_id = database.add_reminder(
            1, 99, "su iç", datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        pending = database.get_pending_reminders()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["message"], "su iç")
        self.assertTrue(database.mark_reminder_sent(reminder_id))
        self.assertEqual(database.get_pending_reminders(), [])

    def test_reminders_are_scoped_and_can_be_cancelled(self):
        from datetime import datetime, timedelta, timezone

        due_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        reminder_id = database.add_reminder(1, 99, "toplantı", due_at)
        database.add_reminder(2, 100, "başka kullanıcı", due_at)

        self.assertEqual(len(database.get_pending_reminders(1)), 1)
        self.assertFalse(database.cancel_reminder(reminder_id, 2))
        self.assertTrue(database.cancel_reminder(reminder_id, 1))
        self.assertEqual(database.get_pending_reminders(1), [])

    def test_user_can_set_default_city(self):
        self.assertEqual(database.get_default_city(1, "Istanbul"), "Istanbul")
        database.set_default_city(1, "Ankara")
        self.assertEqual(database.get_default_city(1), "Ankara")
        database.set_default_city(1, "İzmir")
        self.assertEqual(database.get_default_city(1), "İzmir")


if __name__ == "__main__":
    unittest.main()
