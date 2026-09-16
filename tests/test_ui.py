import unittest

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
                "btn_finance",
                "btn_tasks",
                "btn_notes",
                "btn_quick_add",
                "btn_reminders",
                "btn_help",
            },
        )

    def test_back_button_returns_home(self):
        markup = bot.get_back_keyboard().to_dict()
        self.assertEqual(
            markup["inline_keyboard"][0][0]["callback_data"], "btn_home"
        )

    def test_main_panel_is_compact(self):
        self.assertIn("Kişisel Asistan Paneli", bot.MAIN_MENU_TEXT)
        self.assertLess(len(bot.MAIN_MENU_TEXT), 300)

    def test_webhook_config_does_not_expose_bot_token(self):
        config = bot.get_webhook_config("123:super-secret", "https://bot.example.com/")
        self.assertEqual(config["webhook_url"], "https://bot.example.com/telegram")
        self.assertNotIn("super-secret", config["webhook_url"])
        self.assertEqual(len(config["secret_token"]), 64)

    def test_local_mode_has_no_webhook(self):
        self.assertIsNone(bot.get_webhook_config("token", ""))


if __name__ == "__main__":
    unittest.main()
