import unittest

import httpx

from services.x_trends import XTrendsError, get_x_hashtags


class XTrendsTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_first_two_hashtags_in_rank_order(self):
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer secret")
            self.assertIn("/2/trends/by/woeid/23424969", str(request.url))
            return httpx.Response(200, json={"data": [
                {"trend_name": "Gündem konusu"},
                {"trend_name": "#Bir"},
                {"trend_name": "#Iki"},
                {"trend_name": "#Uc"},
            ]})

        result = await get_x_hashtags(
            "secret", 23424969, transport=httpx.MockTransport(handler)
        )
        self.assertEqual(result, ["#Bir", "#Iki"])

    async def test_missing_token_fails_without_network_request(self):
        with self.assertRaises(XTrendsError):
            await get_x_hashtags("", 1)

    async def test_http_error_is_wrapped(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(401, json={"title": "Unauthorized"})
        )
        with self.assertRaises(XTrendsError):
            await get_x_hashtags("bad", 1, transport=transport)


if __name__ == "__main__":
    unittest.main()
