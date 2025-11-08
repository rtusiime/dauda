from __future__ import annotations

import logging
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

import httpx

from .database import DatabaseSession, SessionLocal
from .models import Channel, EventSource, EventType, Listing

LOGGER = logging.getLogger(__name__)


def _parse_ics_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    if len(value) == 15 and value.count("T") == 1:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    if len(value) == 8:
        dt = datetime.strptime(value, "%Y%m%d")
        return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _parse_ics(content: str) -> Iterable[dict[str, str]]:
    event: dict[str, str] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            event = {}
            continue
        if line == "END:VEVENT":
            if event:
                yield event
            event = None
            continue
        if event is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.startswith("DTSTART"):
            key = "DTSTART"
        elif key.startswith("DTEND"):
            key = "DTEND"
        event[key] = value


def _derive_datetimes(event: dict[str, str]) -> tuple[datetime, datetime]:
    start_raw = event.get("DTSTART")
    end_raw = event.get("DTEND")
    if start_raw is None or end_raw is None:
        raise ValueError("ICS event missing DTSTART or DTEND")
    start = _parse_ics_datetime(start_raw)
    end = _parse_ics_datetime(end_raw)
    if len(start_raw) == 8 and start == end:
        end = start + timedelta(days=1)
    if end <= start:
        end = start + timedelta(hours=12)
    return start, end


class ChannelFeedWorker:
    def __init__(
        self,
        *,
        interval_seconds: int = 300,
        session_factory: Callable[[], DatabaseSession] = SessionLocal,
    ) -> None:
        self._interval = interval_seconds
        self._session_factory = session_factory
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="channel-feed-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            while not self._stop_event.is_set():
                self.sync_once(client)
                self._stop_event.wait(self._interval)

    def sync_once(self, client: httpx.Client | None = None) -> None:
        close_client = False
        if client is None:
            client = httpx.Client(timeout=10.0)
            close_client = True
        try:
            with closing(self._session_factory()) as db:
                listings = db.list_listings()
                for listing in listings:
                    self._sync_listing(db, listing, client)
        finally:
            if close_client:
                client.close()

    def _sync_listing(
        self, db: DatabaseSession, listing: Listing, client: httpx.Client
    ) -> None:
        for link in listing.channel_links:
            if not link.import_url:
                continue
            try:
                response = client.get(link.import_url)
                if response.status_code != 200:
                    LOGGER.warning("Failed to fetch %s: %s", link.import_url, response.status_code)
                    continue
                for parsed in _parse_ics(response.text):
                    try:
                        start, end = _derive_datetimes(parsed)
                    except ValueError as exc:
                        LOGGER.debug("Skipping event due to parse error: %s", exc)
                        continue
                    uid = parsed.get("UID")
                    if uid is None:
                        LOGGER.debug("Skipping event without UID from %s", link.import_url)
                        continue
                    summary = parsed.get("SUMMARY")
                    source = (
                        EventSource.AIRBNB
                        if link.channel == Channel.AIRBNB
                        else EventSource.BOOKING
                    )
                    if db.find_event_by_external_id(listing, source, uid):
                        continue
                    db.create_event(
                        listing,
                        start_utc=start,
                        end_utc=end,
                        event_type=EventType.RESERVATION,
                        source=source,
                        summary=summary,
                        external_res_id=uid,
                    )
            except httpx.HTTPError as exc:  # pragma: no cover - network failure
                LOGGER.warning("Error fetching %s: %s", link.import_url, exc)


def create_channel_worker(interval_seconds: int = 300) -> ChannelFeedWorker:
    return ChannelFeedWorker(interval_seconds=interval_seconds)
