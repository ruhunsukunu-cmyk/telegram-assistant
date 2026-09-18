from datetime import datetime

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


def _running_clothing_advice(feels_like, wind_speed):
    """Koşuda hissedilen sıcaklığa göre kısa ve güvenli bir katman önerisi üret."""
    try:
        temperature = float(feels_like)
    except (TypeError, ValueError):
        return "Rahat koşu kıyafetini seç; çıkmadan önce sıcaklığı tekrar kontrol et."

    if temperature <= 3:
        clothing = "Termal üst, uzun tayt, eldiven ve bereyle kalın giyin."
    elif temperature <= 8:
        clothing = "Uzun tayt ve katmanlı üst giy; ince eldiven iyi olur."
    elif temperature <= 13:
        clothing = "İnce koşu ceketi veya uzun kollu üst giy."
    elif temperature <= 18:
        clothing = "İnce, nefes alan bir üst yeterli; hafif serin başlayabilir."
    else:
        clothing = "İnce ve nefes alan koşu kıyafeti giy."

    try:
        wind = float(wind_speed)
    except (TypeError, ValueError):
        wind = 0
    if wind >= 30:
        clothing += " Rüzgâr çok güçlü; açık parkur yerine korunaklı rota seç."
    elif wind >= 20:
        clothing += " Rüzgâr için ince bir rüzgârlık ekle."
    return clothing


def _running_rain_advice(weather_code, precipitation_probability, precipitation):
    rain_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95}
    try:
        probability = float(precipitation_probability)
    except (TypeError, ValueError):
        probability = 0
    try:
        amount = float(precipitation)
    except (TypeError, ValueError):
        amount = 0
    if weather_code in rain_codes or probability >= 50 or amount >= 0.2:
        return "Yağmurluk giy; ıslak ve kaygan zemine dikkat et."
    if probability >= 25:
        return "Yağmur ihtimali düşük-orta; ince yağmurluk almak mantıklı."
    return "Yağmurluk gerekmiyor."


async def get_running_weather_advice(
    city_name: str = "Istanbul", run_time: str = "07:00"
) -> str:
    """Sabah koşu saatine ait tahmini ve doğrudan giyim tavsiyesini getir."""
    try:
        target_hour = int(run_time.split(":", 1)[0])
    except (AttributeError, TypeError, ValueError):
        target_hour = 7

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            geo_res = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city_name, "count": 1, "language": "tr", "format": "json"},
            )
            geo_res.raise_for_status()
            results = geo_res.json().get("results", [])
            if not results:
                return f"⚠️ Koşu havası için '{city_name}' bulunamadı."

            city = results[0]
            weather_res = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "hourly": (
                        "temperature_2m,apparent_temperature,precipitation_probability,"
                        "precipitation,weather_code,wind_speed_10m"
                    ),
                    "forecast_days": 2,
                    "timezone": "auto",
                },
            )
            weather_res.raise_for_status()
            hourly = weather_res.json().get("hourly", {})
            times = hourly.get("time", [])
            now = datetime.now()
            candidates = []
            for index, value in enumerate(times):
                try:
                    forecast_at = datetime.fromisoformat(value)
                except (TypeError, ValueError):
                    continue
                if forecast_at.date() == now.date() and forecast_at.hour == target_hour:
                    candidates.append((forecast_at, index))
            if not candidates:
                raise ValueError("Koşu saatine ait tahmin bulunamadı")
            _, index = candidates[0]

            def at(field, default="--"):
                values = hourly.get(field, [])
                return values[index] if index < len(values) and values[index] is not None else default

            temperature = at("temperature_2m")
            feels_like = at("apparent_temperature", temperature)
            probability = at("precipitation_probability", 0)
            precipitation = at("precipitation", 0)
            weather_code = at("weather_code", 0)
            wind = at("wind_speed_10m", 0)
            condition, emoji = WEATHER_CODES.get(weather_code, ("Normal", "🌡️"))
            rain_advice = _running_rain_advice(weather_code, probability, precipitation)
            clothing_advice = _running_clothing_advice(feels_like, wind)

            return (
                f"🏃 Sabah koşusu · {run_time}\n"
                f"📍 {city['name']} · {emoji} {condition}\n"
                f"🌡️ {temperature}°C · Hissedilen {feels_like}°C\n"
                f"🌧️ Yağış ihtimali %{probability} · 💨 Rüzgâr {wind} km/sa\n\n"
                f"🧥 {clothing_advice}\n"
                f"☔ {rain_advice}"
            )
    except Exception:
        return (
            "🏃 Sabah koşusu\n"
            "Hava tahmini şu anda alınamadı. Çıkmadan hemen önce hava durumunu kontrol et."
        )
