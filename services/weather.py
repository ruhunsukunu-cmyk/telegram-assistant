import httpx

# WMO Hava Durumu Kodları Tablosu
WEATHER_CODES = {
    0: ("Açık / Güneşli", "☀️"),
    1: ("Çoğunlukla Açık", "🌤️"),
    2: ("Parçalı Bulutlu", "⛅"),
    3: ("Bulutlu", "☁️"),
    45: ("Sisli", "🌫️"),
    48: ("Kırağılı Sis", "🌫️"),
    51: ("Hafif Çiseleme", "🌦️"),
    53: ("Orta Çiseleme", "🌧️"),
    55: ("Yoğun Çiseleme", "🌧️"),
    61: ("Hafif Yağmur", "🌦️"),
    63: ("Yağmurlu", "🌧️"),
    65: ("Kuvvetli Yağmur", "🌧️⛈️"),
    71: ("Hafif Kar Yağışı", "🌨️"),
    73: ("Kar Yağışlı", "❄️"),
    75: ("Yoğun Kar Yağışı", "❄️🌨️"),
    80: ("Sağanak Yağış", "🌦️"),
    81: ("Kuvvetli Sağanak", "🌧️"),
    82: ("Şiddetli Sağanak", "⛈️"),
    95: ("Gök Gürültülü Fırtına", "⚡⛈️"),
}

MET_CONDITIONS = {
    "clearsky": ("Açık / Güneşli", "☀️"),
    "fair": ("Çoğunlukla Açık", "🌤️"),
    "partlycloudy": ("Parçalı Bulutlu", "⛅"),
    "cloudy": ("Bulutlu", "☁️"),
    "fog": ("Sisli", "🌫️"),
    "heavyrain": ("Kuvvetli Yağmur", "🌧️"),
    "lightrain": ("Hafif Yağmur", "🌦️"),
    "rain": ("Yağmurlu", "🌧️"),
    "heavysnow": ("Yoğun Kar Yağışı", "❄️"),
    "lightsnow": ("Hafif Kar Yağışı", "🌨️"),
    "snow": ("Kar Yağışlı", "❄️"),
}


def _met_condition(symbol_code):
    base_code = (symbol_code or "").split("_")[0]
    for key, value in MET_CONDITIONS.items():
        if key in base_code:
            return value
    return ("Normal", "🌡️")


async def _get_met_weather(client, lat, lon):
    """Open-Meteo kotalandığında MET Norway verisini kullan."""
    response = await client.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/compact",
        params={"lat": round(lat, 4), "lon": round(lon, 4)},
        headers={"User-Agent": "telegram-assistant-bot/1.0 github.com/ruhunsukunu-cmyk/telegram-assistant"},
    )
    response.raise_for_status()
    timeseries = response.json().get("properties", {}).get("timeseries", [])
    if not timeseries:
        raise ValueError("Yedek hava durumu servisi boş yanıt verdi")

    entry = timeseries[0]["data"]
    details = entry["instant"]["details"]
    next_hour = entry.get("next_1_hours", {}).get("summary", {})
    condition, emoji = _met_condition(next_hour.get("symbol_code"))
    return {
        "temperature": details.get("air_temperature", "--"),
        "humidity": details.get("relative_humidity", "--"),
        "wind": details.get("wind_speed", "--"),
        "condition": condition,
        "emoji": emoji,
    }


async def get_weather(city_name: str = "Istanbul") -> str:
    """Open-Meteo API ile ücretsiz, anahtarsız hava durumu çeker."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Şehir koordinatlarını bul (Geocoding API - Ücretsiz)
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = await client.get(
                geo_url,
                params={"name": city_name, "count": 1, "language": "tr", "format": "json"},
            )
            geo_res.raise_for_status()
            geo_data = geo_res.json()

            if not geo_data.get("results"):
                return f"❌ '{city_name}' şehri bulunamadı. Lütfen geçerli bir şehir adı yazın."

            city_info = geo_data["results"][0]
            lat = city_info["latitude"]
            lon = city_info["longitude"]
            resolved_city = city_info["name"]
            country = city_info.get("country", "")

            # 2. Hava durumu verisini çek (Forecast API - Ücretsiz)
            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_res = await client.get(
                weather_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                },
            )
            if weather_res.status_code == 429:
                current = await _get_met_weather(client, lat, lon)
                temp = current["temperature"]
                humidity = current["humidity"]
                wind = current["wind"]
                condition = current["condition"]
                emoji = current["emoji"]
            else:
                weather_res.raise_for_status()
                weather_data = weather_res.json()
                current = weather_data.get("current", {})
                temp = current.get("temperature_2m", "--")
                humidity = current.get("relative_humidity_2m", "--")
                wind = current.get("wind_speed_10m", "--")
                w_code = current.get("weather_code", 0)
                condition, emoji = WEATHER_CODES.get(w_code, ("Normal", "🌡️"))

            return (
                f"📍 *{resolved_city}, {country}* {emoji}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🌡️ *Sıcaklık:* `{temp}°C`\n"
                f"🌤️ *Durum:* {condition}\n"
                f"💧 *Nem:* `%{humidity}`\n"
                f"💨 *Rüzgar:* `{wind} km/h`"
            )
    except Exception:
        return "⚠️ Hava durumu servisleri şu anda yoğun. Lütfen kısa bir süre sonra tekrar deneyin."
