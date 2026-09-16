import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from services.calendar_sync import parse_ical_events
from services.finance import format_price, get_market_rates
from services.weather import get_weather
from services.gemini import (
    GeminiConfigurationError,
    GeminiRateLimitError,
    generate_text,
)


class AsyncClientContext:
    def __init__(self, responses):
        self.responses = iter(responses)

    async def __aenter__(self):
        client = MagicMock()
        client.get = AsyncMock(side_effect=self.responses)
        return client

    async def __aexit__(self, *args):
        return False


def response(payload):
    result = MagicMock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_success(self):
        async def handler(request):
            self.assertEqual(request.headers["x-goog-api-key"], "test-key")
            self.assertNotIn("test-key", str(request.url))
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "Merhaba!"}]}}]},
            )

        transport = httpx.MockTransport(handler)
        result = await generate_text(
            "test-key", "Nasılsın?", "Türkçe yanıtla", transport=transport
        )
        self.assertEqual(result, "Merhaba!")

    async def test_gemini_rate_limit_is_distinct(self):
        async def handler(request):
            return httpx.Response(429, json={"error": {}})

        with self.assertRaises(GeminiRateLimitError):
            await generate_text(
                "test-key", "Soru", "Yanıtla",
                transport=httpx.MockTransport(handler),
            )

    async def test_gemini_rejects_invalid_model_name(self):
        with self.assertRaises(GeminiConfigurationError):
            await generate_text("test-key", "Soru", "Yanıtla", model="bad/model")

    def test_ical_event_is_normalized_and_keyed(self):
        content = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:test-event\r
DTSTART:20260918T090000Z\r
DTEND:20260918T100000Z\r
SUMMARY:Doktor randevusu\r
END:VEVENT\r
END:VCALENDAR\r
"""
        events = parse_ical_events(
            content,
            datetime(2026, 9, 18, tzinfo=timezone.utc),
            datetime(2026, 9, 19, tzinfo=timezone.utc),
            ZoneInfo("Europe/Istanbul"),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Doktor randevusu")
        self.assertEqual(events[0].starts_at.hour, 9)
        self.assertEqual(len(events[0].key), 64)

    def test_format_price_handles_missing_values(self):
        self.assertEqual(format_price("--"), "--")
        self.assertEqual(format_price(1234567), "1,234,567")

    async def test_weather_success(self):
        responses = [
            response({"results": [{"latitude": 41, "longitude": 29, "name": "Istanbul", "country": "Türkiye"}]}),
            response({"current": {"temperature_2m": 20, "relative_humidity_2m": 50, "wind_speed_10m": 8, "weather_code": 0}}),
        ]
        with patch("services.weather.httpx.AsyncClient", return_value=AsyncClientContext(responses)):
            result = await get_weather("Istanbul")
        self.assertIn("20°C", result)
        self.assertIn("Açık / Güneşli", result)

    async def test_weather_city_not_found(self):
        with patch("services.weather.httpx.AsyncClient", return_value=AsyncClientContext([response({})])):
            result = await get_weather("yok")
        self.assertIn("bulunamadı", result)

    async def test_weather_falls_back_when_open_meteo_is_rate_limited(self):
        limited = response({})
        limited.status_code = 429
        met = response({
            "properties": {"timeseries": [{"data": {
                "instant": {"details": {
                    "air_temperature": 18.5,
                    "relative_humidity": 61,
                    "wind_speed": 3.2,
                }},
                "next_1_hours": {"summary": {"symbol_code": "partlycloudy_day"}},
            }}]}
        })
        responses = [
            response({"results": [{"latitude": 41, "longitude": 29, "name": "Istanbul", "country": "Türkiye"}]}),
            limited,
            met,
        ]
        with patch("services.weather.httpx.AsyncClient", return_value=AsyncClientContext(responses)):
            result = await get_weather("Istanbul")
        self.assertIn("18.5°C", result)
        self.assertIn("Parçalı Bulutlu", result)

    async def test_finance_missing_crypto_values_do_not_crash(self):
        responses = [response({"rates": {"USD": 0.025, "EUR": 0.023, "GBP": 0.02}}), response({})]
        with patch("services.finance.httpx.AsyncClient", return_value=AsyncClientContext(responses)):
            result = await get_market_rates()
        self.assertIn("Bitcoin (BTC):* `$--`", result)


if __name__ == "__main__":
    unittest.main()
