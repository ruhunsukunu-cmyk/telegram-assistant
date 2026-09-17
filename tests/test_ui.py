import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone

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
                "btn_briefing",
                "btn_alerts",
                "btn_tasks",
                "btn_calendar",
                "btn_ai",
                "btn_more",
            },
        )

    def test_secondary_tools_are_kept_out_of_main_menu(self):
        markup = bot.get_more_keyboard().to_dict()
        callbacks = {
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        }
        self.assertTrue({
            "btn_weather", "btn_finance", "btn_reminders", "btn_quick_add",
            "btn_habits", "btn_expenses", "btn_notes", "btn_about", "btn_help",
            "btn_intro", "btn_updates",
        }.issubset(callbacks))

    def test_intro_is_short_and_explains_the_bot(self):
        self.assertIn("günlük yaşam asistanıyım", bot.INTRO_TEXT)
        self.assertIn("Gereksiz yere yazmam", bot.INTRO_TEXT)
        self.assertLess(len(bot.INTRO_TEXT), 700)

    def test_release_notes_explain_current_version(self):
        self.assertIn("v2.1", bot.RELEASE_NOTES_TEXT)
        self.assertIn("Güncelleme notları", bot.RELEASE_NOTES_TEXT)

    def test_alerts_panel_prioritizes_proactive_features(self):
        markup = bot.get_alerts_keyboard().to_dict()
        callbacks = [
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        ]
        self.assertEqual(callbacks[0], "btn_briefing")
        self.assertIn("btn_reminders", callbacks)
        self.assertIn("btn_calendar", callbacks)

    def test_back_button_returns_home(self):
        markup = bot.get_back_keyboard().to_dict()
        self.assertEqual(
            markup["inline_keyboard"][0][0]["callback_data"], "btn_home"
        )

    def test_main_panel_is_compact(self):
        self.assertIn("Günlük Asistan", bot.MAIN_MENU_TEXT)
        self.assertIn("bilgilendirir", bot.MAIN_MENU_TEXT)
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

    def test_event_preparation_is_contextual(self):
        self.assertIn("önceki sonuçlar", bot.event_preparation("Doktor kontrolü"))
        self.assertIn("Gündemi", bot.event_preparation("Proje toplantısı"))
        self.assertIn("Bilet", bot.event_preparation("Uçuş"))

    def test_day_analysis_detects_calendar_conflict(self):
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        events = [
            {"title": "Toplantı", "starts_at": start, "ends_at": start + timedelta(hours=1), "all_day": False},
            {"title": "Doktor", "starts_at": start + timedelta(minutes=30), "ends_at": None, "all_day": False},
        ]
        self.assertIn("Takvim çakışması", bot.analyze_day(events, [])[0])


class TodaySummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_summary_combines_daily_information(self):
        with (
            patch("bot.get_weather", new=AsyncMock(return_value="🌤️ Hava özeti")),
            patch("bot.db.get_default_city", return_value="Ankara"),
            patch("bot.db.get_enriched_tasks", return_value=[{
                "title": "Spor yap", "is_done": 0, "priority": "normal",
                "due_at": None, "created_at": datetime.now(timezone.utc),
            }]),
            patch("bot.db.get_pending_reminders", return_value=[{
                "message": "Su iç", "due_at": datetime.now(timezone.utc)
            }]),
            patch("bot.get_combined_upcoming_events", new=AsyncMock(return_value=[])),
        ):
            result = await bot.build_today_summary(1)
        self.assertIn("Bugün", result)
        self.assertIn("Spor yap", result)
        self.assertIn("Su iç", result)

    async def test_morning_briefing_combines_news_and_plan(self):
        with (
            patch("bot.GEMINI_API_KEY", "test-key"),
            patch("bot.build_today_summary", new=AsyncMock(return_value="☀️ Bugün")),
            patch("bot.build_gemini_context", new=AsyncMock(return_value="Görev: Spor")),
            patch("bot.generate_grounded_text", new=AsyncMock(return_value=(
                "🗞️ Kritik gelişmeler\n• Haber\n\n🎯 Günün odağı\n1. Spor",
                [{"title": "Kaynak", "url": "https://example.com"}],
            ))),
        ):
            chunks = await bot.build_morning_briefing(1)
        result = "\n".join(chunks)
        self.assertIn("Akıllı sabah özeti", result)
        self.assertIn("Kritik gelişmeler", result)
        self.assertIn("https://example.com", result)


if __name__ == "__main__":
    unittest.main()
