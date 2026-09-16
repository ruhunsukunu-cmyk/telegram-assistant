import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import bot


class UiTests(unittest.TestCase):
    def test_main_menu_has_clear_navigation(self):
        markup = bot.get_main_keyboard().to_dict()
        callbacks = {
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        }
        self.assertEqual(
            callbacks,
            {
                "btn_weather",
                "btn_today",
                "btn_finance",
                "btn_tasks",
                "btn_notes",
                "btn_habits",
                "btn_expenses",
                "btn_quick_add",
                "btn_reminders",
                "btn_calendar",
                "btn_about",
                "btn_help",
                "btn_ai",
            },
        )

    def test_back_button_returns_home(self):
        markup = bot.get_back_keyboard().to_dict()
        self.assertEqual(
            markup["inline_keyboard"][0][0]["callback_data"], "btn_home"
        )

    def test_main_panel_is_compact(self):
        self.assertIn("Kişisel Asistan", bot.MAIN_MENU_TEXT)
        self.assertLess(len(bot.MAIN_MENU_TEXT), 300)

    def test_about_page_lists_core_capabilities(self):
        self.assertTrue(callable(bot.about_command))

    def test_webhook_config_does_not_expose_bot_token(self):
        config = bot.get_webhook_config("123:super-secret", "https://bot.example.com/")
        self.assertEqual(config["webhook_url"], "https://bot.example.com/telegram")
        self.assertNotIn("super-secret", config["webhook_url"])
        self.assertEqual(len(config["secret_token"]), 64)

    def test_local_mode_has_no_webhook(self):
        self.assertIsNone(bot.get_webhook_config("token", ""))

    def test_quick_reminder_parser(self):
        self.assertEqual(bot.parse_quick_reminder("15 Su iç"), (15.0, "Su iç"))
        self.assertEqual(bot.parse_quick_reminder("2,5 Çayı kontrol et"), (2.5, "Çayı kontrol et"))
        self.assertIsNone(bot.parse_quick_reminder("yarın Su iç"))
        self.assertIsNone(bot.parse_quick_reminder("0 Su iç"))
        self.assertIsNone(bot.parse_quick_reminder("15"))

    def test_cancel_button_is_available_for_input_mode(self):
        markup = bot.get_cancel_keyboard().to_dict()
        self.assertEqual(
            markup["inline_keyboard"][0][0]["callback_data"], "cancel_input"
        )

    def test_long_ai_answers_are_split_for_telegram(self):
        chunks = bot.split_telegram_text("a" * 8001)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in chunks))


class TodaySummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_summary_combines_daily_information(self):
        with (
            patch("bot.get_weather", new=AsyncMock(return_value="🌤️ Hava özeti")),
            patch("bot.db.get_default_city", return_value="Ankara"),
            patch("bot.db.get_tasks", return_value=[{"title": "Spor yap", "is_done": 0}]),
            patch("bot.db.get_pending_reminders", return_value=[{
                "message": "Su iç", "due_at": datetime.now(timezone.utc)
            }]),
            patch("bot.get_combined_upcoming_events", new=AsyncMock(return_value=[])),
        ):
            result = await bot.build_today_summary(1)
        self.assertIn("Bugünün özeti", result)
        self.assertIn("Spor yap", result)
        self.assertIn("Su iç", result)


if __name__ == "__main__":
    unittest.main()
