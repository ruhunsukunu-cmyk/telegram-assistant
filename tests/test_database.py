import os
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
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

    def test_sqlite_creates_configured_parent_directory(self):
        nested_path = os.path.join(self.temp_dir.name, "volume", "assistant.db")
        with patch.object(database, "DB_PATH", nested_path):
            database.init_db()
        self.assertTrue(os.path.isfile(nested_path))

    def test_storage_label_distinguishes_persistent_sqlite(self):
        with patch.dict(os.environ, {"DB_PATH": "/data/assistant.db"}):
            self.assertEqual(database.storage_label(), "kalıcı SQLite")

    def test_postgres_values_are_converted_for_sqlite(self):
        self.assertEqual(database._sqlite_value(Decimal("12.50")), "12.50")
        self.assertEqual(
            database._sqlite_value(datetime(2026, 9, 17, 12, 30)),
            "2026-09-17 12:30:00",
        )

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

    def test_search_is_scoped_to_user(self):
        database.add_task(1, "Doktor randevusu al")
        database.add_note(1, "Doktor telefon numarası")
        database.add_note(2, "Doktor özel notu")
        results = database.search_user_content(1, "Doktor")
        self.assertEqual(len(results), 2)
        self.assertEqual({item["type"] for item in results}, {"task", "note"})

    def test_clear_completed_tasks_keeps_pending_and_other_users(self):
        done_id = database.add_task(1, "Biten görev")
        database.complete_task(done_id, 1)
        database.add_task(1, "Bekleyen görev")
        other_id = database.add_task(2, "Başkasının biten görevi")
        database.complete_task(other_id, 2)

        self.assertEqual(database.clear_completed_tasks(1), 1)
        self.assertEqual([row["title"] for row in database.get_tasks(1)], ["Bekleyen görev"])
        self.assertEqual(len(database.get_tasks(2)), 1)

    def test_extended_daily_life_data(self):
        from datetime import datetime, timedelta, timezone

        task_id = database.add_task(1, "Raporu bitir")
        database.set_task_metadata(task_id, 1, "high", datetime.now(timezone.utc) + timedelta(days=1))
        self.assertEqual(database.get_enriched_tasks(1)[0]["priority"], "high")

        habit_id = database.add_habit(1, "Kitap oku")
        self.assertTrue(database.check_habit(habit_id, 1, "2026-09-16"))
        self.assertEqual(database.get_habits(1, "2026-09-16")[0]["done_today"], 1)

        database.add_expense(1, 250, "market", "haftalık alışveriş")
        self.assertEqual(float(database.get_expense_summary(1)[0]["total"]), 250)
        self.assertEqual(len(database.get_expenses(1)), 1)
        database.set_budget(1, 5000)
        self.assertEqual(float(database.get_budget(1)["monthly_limit"]), 5000)

        database.add_calendar_event(1, "Doktor", datetime.now(timezone.utc) + timedelta(days=2))
        self.assertEqual(database.get_upcoming_events(1)[0]["title"], "Doktor")

        exported = database.export_user_data(1)
        self.assertEqual(len(exported["tasks"]), 1)
        self.assertEqual(len(exported["expenses"]), 1)

        reminder_id = database.add_reminder(1, 99, "Günlük su", datetime.now(timezone.utc) + timedelta(hours=1))
        database.set_reminder_recurrence(reminder_id, 1, "daily")
        self.assertEqual(database.get_reminder_recurrence(reminder_id), "daily")

        database.set_daily_summary(1, 99, "08:00")
        self.assertEqual(database.get_daily_summaries()[0]["send_time"], "08:00")

    def test_calendar_notification_is_sent_only_once(self):
        self.assertFalse(database.was_calendar_notification_sent("event-key", 30))
        self.assertTrue(database.mark_calendar_notification_sent("event-key", 30))
        self.assertFalse(database.mark_calendar_notification_sent("event-key", 30))
        self.assertTrue(database.was_calendar_notification_sent("event-key", 30))

    def test_calendar_notification_offsets_are_tracked_independently(self):
        self.assertTrue(database.mark_calendar_notification_sent("event-key", 1440))
        self.assertFalse(database.was_calendar_notification_sent("event-key", 120))
        self.assertTrue(database.mark_calendar_notification_sent("event-key", 120))
        self.assertTrue(database.was_calendar_notification_sent("event-key", 1440))
        self.assertTrue(database.was_calendar_notification_sent("event-key", 120))

    def test_actionable_alert_records_feedback(self):
        alert = database.create_assistant_alert(1, 99, "calendar", "event-1", "Doktor")
        same_alert = database.create_assistant_alert(1, 99, "calendar", "event-1", "Doktor")
        self.assertEqual(alert["id"], same_alert["id"])
        self.assertTrue(database.resolve_assistant_alert(alert["id"], 1, "snoozed", "snooze_10"))
        self.assertEqual(database.get_feedback_summary(1)["snooze_10"], 1)

    def test_completed_tasks_are_counted_for_review(self):
        from datetime import timedelta, timezone

        task_id = database.add_task(1, "Haftalık iş")
        database.complete_task(task_id, 1)
        self.assertEqual(
            database.count_completed_tasks_since(1, datetime.now(timezone.utc) - timedelta(days=1)),
            1,
        )

    def test_notification_preferences_use_quiet_defaults(self):
        self.assertTrue(database.notification_enabled(1, "morning"))
        self.assertTrue(database.notification_enabled(1, "news"))
        self.assertTrue(database.notification_enabled(1, "calendar"))
        self.assertFalse(database.notification_enabled(1, "midday"))
        self.assertFalse(database.notification_enabled(1, "evening"))
        self.assertFalse(database.notification_enabled(1, "weekly"))
        self.assertFalse(database.notification_enabled(1, "followup"))
        database.set_notification_enabled(1, "midday", True)
        self.assertTrue(database.notification_enabled(1, "midday"))

    def test_onboarding_is_shown_only_once(self):
        self.assertFalse(database.has_seen_onboarding(1))
        database.mark_onboarding_seen(1)
        database.mark_onboarding_seen(1)
        self.assertTrue(database.has_seen_onboarding(1))

    def test_app_metadata_is_persistent_and_updatable(self):
        self.assertIsNone(database.get_app_metadata("release"))
        self.assertEqual(database.get_app_metadata("missing", "fallback"), "fallback")
        database.set_app_metadata("release", "2.4")
        self.assertEqual(database.get_app_metadata("release"), "2.4")
        database.set_app_metadata("release", "2.5")
        self.assertEqual(database.get_app_metadata("release"), "2.5")

    def test_delete_user_data_removes_owned_records(self):
        database.add_note(1, "özel not")
        database.add_task(1, "özel görev")
        database.add_note(2, "korunacak not")
        database.delete_user_data(1)
        self.assertEqual(database.get_notes(1), [])
        self.assertEqual(database.get_tasks(1), [])
        self.assertEqual(len(database.get_notes(2)), 1)


if __name__ == "__main__":
    unittest.main()
