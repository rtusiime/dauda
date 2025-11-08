from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Channel, Event, EventSource, EventType, Listing


def _format_date(dt: datetime, tz: ZoneInfo) -> str:
    localized = dt.astimezone(tz)
    return localized.date().strftime("%Y%m%d")


def event_summary(event: Event) -> str:
    if event.type == EventType.BLOCK:
        return "BLOCK"
    if event.source == EventSource.AIRBNB:
        return "Airbnb Reservation"
    if event.source == EventSource.BOOKING:
        return "Booking Reservation"
    return event.summary or "Reservation"


def build_ics(listing: Listing, channel: Channel, events: list[Event]) -> str:
    tz = ZoneInfo(listing.timezone)
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Dauda//Channel Sync//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for event in events:
        # Convert to date boundaries in listing timezone
        start_date = _format_date(event.start_utc, tz)
        # For all-day ICS, dtend should be next day to represent inclusive range
        end_date_dt = event.end_utc.astimezone(tz)
        # Guarantee at least one day
        if end_date_dt <= event.start_utc.astimezone(tz):
            end_date_dt = event.start_utc.astimezone(tz) + timedelta(days=1)
        end_date = end_date_dt.date().strftime("%Y%m%d")
        uid = f"{event.id}@dauda"
        summary = event_summary(event)
        last_modified = event.created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{start_date}",
                f"DTEND;VALUE=DATE:{end_date}",
                f"SUMMARY:{summary}",
                f"LAST-MODIFIED:{last_modified}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def events_for_channel(channel: Channel, events: list[Event]) -> list[Event]:
    relevant_sources: set[EventSource]
    if channel == Channel.AIRBNB:
        relevant_sources = {EventSource.MANUAL, EventSource.BOOKING}
    elif channel == Channel.BOOKING:
        relevant_sources = {EventSource.MANUAL, EventSource.AIRBNB}
    else:
        relevant_sources = {EventSource.MANUAL}

    return [
        event
        for event in events
        if not event.is_shadowed and (event.source in relevant_sources or event.type == EventType.BLOCK)
    ]
