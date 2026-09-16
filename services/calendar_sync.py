"""Read-only iCalendar feed integration for the personal assistant."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from hashlib import sha256

import httpx
from icalendar import Calendar
import recurring_ical_events


@dataclass(frozen=True)
class CalendarEvent:
    key: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool = False


def _as_datetime(value, local_timezone):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=local_timezone)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=local_timezone)
    raise ValueError("Unsupported calendar date value")


def parse_ical_events(content, range_start, range_end, local_timezone):
    """Expand recurring entries and return normalized events in UTC."""
    calendar = Calendar.from_ical(content)
    components = recurring_ical_events.of(calendar).between(range_start, range_end)
    events = []
    for component in components:
        raw_start = component.decoded("DTSTART")
        raw_end = component.decoded("DTEND") if component.get("DTEND") else None
        starts_at = _as_datetime(raw_start, local_timezone).astimezone(timezone.utc)
        ends_at = (
            _as_datetime(raw_end, local_timezone).astimezone(timezone.utc)
            if raw_end is not None else None
        )
        title = str(component.get("SUMMARY", "İsimsiz etkinlik")).strip()
        uid = str(component.get("UID", title)).strip()
        instance = starts_at.isoformat()
        key = sha256(f"{uid}|{instance}".encode("utf-8")).hexdigest()
        events.append(
            CalendarEvent(
                key=key,
                title=title[:300],
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=isinstance(raw_start, date) and not isinstance(raw_start, datetime),
            )
        )
    return sorted(events, key=lambda event: event.starts_at)


async def fetch_ical_events(feed_url, range_start, range_end, local_timezone):
    if not feed_url:
        return []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
    return parse_ical_events(response.content, range_start, range_end, local_timezone)
