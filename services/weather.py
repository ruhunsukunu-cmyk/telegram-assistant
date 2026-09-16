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


async def get_weather(city_name: str = "Istanbul") -> str:
    """Open-Meteo API ile ücretsiz, anahtarsız hava durumu çeker."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Şehir koordinatlarını bul (Geocoding API - Ücretsiz)
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=tr&format=json"
            geo_res = await client.get(geo_url)
            geo_data = geo_res.json()

            if not geo_data.get("results"):
                return f"❌ '{city_name}' şehri bulunamadı. Lütfen geçerli bir şehir adı yazın."

            city_info = geo_data["results"][0]
            lat = city_info["latitude"]
            lon = city_info["longitude"]
            resolved_city = city_info["name"]
            country = city_info.get("country", "")

            # 2. Hava durumu verisini çek (Forecast API - Ücretsiz)
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            )
            weather_res = await client.get(weather_url)
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
    except Exception as e:
        return f"⚠️ Hava durumu bilgisi alınırken bir hata oluştu: {str(e)}"
