import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.finance import format_price, get_market_rates
from services.weather import get_weather


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

    async def test_finance_missing_crypto_values_do_not_crash(self):
        responses = [response({"rates": {"USD": 0.025, "EUR": 0.023, "GBP": 0.02}}), response({})]
        with patch("services.finance.httpx.AsyncClient", return_value=AsyncClientContext(responses)):
            result = await get_market_rates()
        self.assertIn("Bitcoin (BTC):* `$--`", result)


if __name__ == "__main__":
    unittest.main()
