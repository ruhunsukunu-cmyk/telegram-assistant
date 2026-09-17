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
                "btn_news",
                "btn_calendar",
                "btn_settings",
            },
        )

    def test_settings_keeps_secondary_navigation_available(self):
        markup = bot.get_settings_keyboard().to_dict()
        callbacks = {
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        }
        self.assertTrue({
            "btn_alerts", "btn_intro", "btn_updates", "btn_about", "btn_more"
        }.issubset(callbacks))

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
        }.issubset(callbacks))

    def test_intro_is_short_and_explains_the_bot(self):
        self.assertIn("kişisel asistanım", bot.INTRO_TEXT)
        self.assertIn("Gereksiz yere yazmam", bot.INTRO_TEXT)
        self.assertLess(len(bot.INTRO_TEXT), 700)

    def test_release_notes_explain_current_version(self):
        self.assertIn("v2.2", bot.RELEASE_NOTES_TEXT)
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
        self.assertIn("Bugün neyi bilmen gerekiyor", bot.MAIN_MENU_TEXT)
        self.assertIn("önemli haberleri", bot.MAIN_MENU_TEXT)
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

    async def test_morning_briefing_only_contains_personal_plan(self):
        generated = AsyncMock(return_value="🎯 Günün odağı\n1. Spor")
        with (
            patch("bot.GEMINI_API_KEY", "test-key"),
            patch("bot.build_today_summary", new=AsyncMock(return_value="☀️ Bugün")),
            patch("bot.build_gemini_context", new=AsyncMock(return_value="Görev: Spor")),
            patch("bot.generate_text", new=generated),
        ):
            chunks = await bot.build_morning_briefing(1)
        result = "\n".join(chunks)
        self.assertIn("Akıllı sabah özeti", result)
        self.assertIn("Günün odağı", result)
        self.assertNotIn("Kritik gelişmeler", result)
        self.assertNotIn("hashtag", generated.await_args.args[1])

    async def test_news_digest_contains_five_turkey_and_world_headlines(self):
        grounded = AsyncMock(return_value=(
            "🇹🇷 Türkiye — En önemli 5 haber\n"
            "1. Haber 1\n2. Haber 2\n3. Haber 3\n4. Haber 4\n5. Haber 5\n\n"
            "🌍 Dünya — En önemli 5 haber\n"
            "1. World 1\n2. World 2\n3. World 3\n4. World 4\n5. World 5",
            [{"title": "Reuters", "url": "https://example.com/news"}],
        ))
        with (
            patch("bot.GEMINI_API_KEY", "test-key"),
            patch("bot.generate_grounded_text", new=grounded),
        ):
            chunks = await bot.build_news_digest()
        result = "\n".join(chunks)
        self.assertEqual(len(chunks), 2)
        self.assertIn("Türkiye — En önemli 5 haber", result)
        self.assertIn("Dünya — En önemli 5 haber", result)
        self.assertIn("Kaynaklar: Reuters", result)
        self.assertNotIn("https://", result)
        prompt = grounded.await_args.args[1]
        self.assertIn("geniş toplumsal etki", prompt)
        self.assertIn("Reuters, AP, AFP", prompt)
        self.assertIn("aynı olayın tekrarlarını alma", prompt)
        self.assertIn("en fazla 120 karakter", prompt)

    async def test_news_digest_retries_when_gemini_output_is_incomplete(self):
        incomplete = (
            "🇹🇷 Türkiye — En önemli 5 haber\n1. Haber 1\n2. Yarım",
            [],
        )
        complete = (
            "🇹🇷 Türkiye — En önemli 5 haber\n"
            "1. T1\n2. T2\n3. T3\n4. T4\n5. T5\n\n"
            "🌍 Dünya — En önemli 5 haber\n"
            "1. D1\n2. D2\n3. D3\n4. D4\n5. D5",
            [],
        )
        grounded = AsyncMock(side_effect=[incomplete, complete])
        with (
            patch("bot.GEMINI_API_KEY", "test-key"),
            patch("bot.generate_grounded_text", new=grounded),
        ):
            chunks = await bot.build_news_digest()
        self.assertEqual(grounded.await_count, 2)
        self.assertEqual(len(chunks), 2)
        self.assertIn("5. D5", chunks[1])


if __name__ == "__main__":
    unittest.main()
