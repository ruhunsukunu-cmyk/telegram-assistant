"""Minimal, dependency-free Gemini REST client used by the Telegram bot."""

import re

import httpx


class GeminiError(RuntimeError):
    """Base error for Gemini API failures."""


class GeminiRateLimitError(GeminiError):
    """Raised when the Gemini API quota or request limit is exceeded."""


class GeminiConfigurationError(GeminiError):
    """Raised when the API key or model configuration is invalid."""


async def generate_text(
    api_key,
    prompt,
    system_instruction,
    model="gemini-2.5-flash",
    max_output_tokens=900,
    transport=None,
):
    """Generate a text response through Gemini's official REST API."""
    if not api_key:
        raise GeminiConfigurationError("Gemini API anahtarı tanımlı değil.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model or ""):
        raise GeminiConfigurationError("Geçersiz Gemini model adı.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.45,
            "maxOutputTokens": max(100, min(int(max_output_tokens), 4096)),
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=35,
            follow_redirects=True,
            transport=transport,
        ) as client:
            response = await client.post(
                url,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise GeminiError("Gemini servisine ulaşılamadı.") from exc

    if response.status_code == 429:
        raise GeminiRateLimitError("Gemini kullanım limiti doldu.")
    if response.status_code in {400, 401, 403, 404}:
        raise GeminiConfigurationError(
            "Gemini API anahtarı veya model ayarı doğrulanamadı."
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise GeminiError("Gemini geçici bir servis hatası döndürdü.") from exc

    try:
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "\n".join(part["text"] for part in parts if part.get("text")).strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiError("Gemini yanıt üretemedi.") from exc
    if not text:
        raise GeminiError("Gemini boş yanıt döndürdü.")
    return text
