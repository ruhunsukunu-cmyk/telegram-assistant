import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from services.natural_language import extract_future_datetime, parse_expense_text


class NaturalLanguageTests(unittest.TestCase):
    def test_extracts_turkish_relative_datetime(self):
        now = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul"))
        value, message = extract_future_datetime("yarın saat 10 doktoru hatırlat", now)
        self.assertEqual(value.strftime("%Y-%m-%d %H:%M"), "2026-09-17 10:00")
        self.assertEqual(message, "doktoru")

    def test_parses_expense(self):
        self.assertEqual(
            parse_expense_text("250 TL market haftalık alışveriş"),
            {"amount": 250.0, "category": "market", "note": "haftalık alışveriş"},
        )

    def test_rejects_non_expense(self):
        self.assertIsNone(parse_expense_text("bugün markete gittim"))


if __name__ == "__main__":
    unittest.main()
