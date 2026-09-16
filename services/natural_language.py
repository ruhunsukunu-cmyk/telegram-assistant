import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser
from dateparser.search import search_dates


DATE_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "TIMEZONE": "Europe/Istanbul",
}


def parse_datetime(text, now=None):
    settings = dict(DATE_SETTINGS)
    if now is not None:
        settings["RELATIVE_BASE"] = now
    return dateparser.parse(text, languages=["tr"], settings=settings)


def parse_expense_text(text):
    match = re.match(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*(?:tl|try|₺)?\s+([^\s]+)(?:\s+(.*))?$", text, re.I)
    if not match:
        return None
    return {
        "amount": float(match.group(1).replace(",", ".")),
        "category": match.group(2).lower(),
        "note": (match.group(3) or "").strip(),
    }


def extract_future_datetime(text, now=None):
    base = now or datetime.now(ZoneInfo("Europe/Istanbul"))
    simple = re.search(r"\b(bugün|bugun|yarın|yarin)\s*(?:saat\s*)?(\d{1,2})(?::(\d{2}))?", text, re.I)
    if simple:
        day_word, hour, minute = simple.groups()
        value = base.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
        if day_word.lower() in {"yarın", "yarin"}:
            value += timedelta(days=1)
        remaining = text[:simple.start()] + " " + text[simple.end():]
        remaining = re.sub(r"\b(hatırlat|hatirlat|etkinlik|takvime ekle)\b", " ", remaining, flags=re.I)
        return value, re.sub(r"\s+", " ", remaining).strip(" ,.-")

    settings = dict(DATE_SETTINGS)
    if now is not None:
        settings["RELATIVE_BASE"] = now
    matches = search_dates(text, languages=["tr"], settings=settings) or []
    if not matches:
        return None
    phrase, value = matches[0]
    remaining = text.replace(phrase, " ", 1)
    remaining = re.sub(r"\b(hatırlat|hatirlat|etkinlik|takvime ekle|saat)\b", " ", remaining, flags=re.I)
    remaining = re.sub(r"\s+", " ", remaining).strip(" ,.-")
    return value, remaining
