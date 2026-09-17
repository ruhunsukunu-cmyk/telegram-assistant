import httpx


class XTrendsError(RuntimeError):
    """Raised when X trends cannot be retrieved or parsed."""


async def get_x_hashtags(bearer_token, woeid, limit=2, transport=None):
    """Return the highest-ranked hashtag trends for an X WOEID location."""
    token = (bearer_token or "").strip()
    if not token:
        raise XTrendsError("X API bearer token is not configured")

    client_kwargs = {"timeout": 10.0}
    if transport is not None:
        client_kwargs["transport"] = transport

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(
                f"https://api.x.com/2/trends/by/woeid/{int(woeid)}",
                params={"max_trends": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            data = response.json().get("data", [])
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise XTrendsError("X trends request failed") from exc

    hashtags = []
    for item in data:
        name = str(item.get("trend_name", "")).strip()
        if name.startswith("#") and name not in hashtags:
            hashtags.append(name)
        if len(hashtags) >= limit:
            break
    return hashtags
