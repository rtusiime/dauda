from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .config import settings
from .models import Channel, ChannelLink, Conflict, ConflictStatus, Event, EventSource, EventType, Listing


class Database:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.listings: Dict[int, Listing] = {}
        self.channel_links: Dict[int, ChannelLink] = {}
        self.channel_links_by_listing: Dict[Tuple[int, Channel], int] = {}
        self.channel_links_by_token: Dict[str, int] = {}
        self.events: Dict[int, Event] = {}
        self.events_by_listing: Dict[int, List[int]] = {}
        self.conflicts: Dict[int, Conflict] = {}
        self._counters = {"listing": 0, "channel_link": 0, "event": 0, "conflict": 0}

    def _next_id(self, name: str) -> int:
        self._counters[name] += 1
        return self._counters[name]

    def create_listing(self, name: str, timezone_name: str) -> Listing:
        listing_id = self._next_id("listing")
        listing = Listing(id=listing_id, name=name, timezone=timezone_name)
        self.listings[listing_id] = listing
        return listing

    def list_listings(self) -> List[Listing]:
        return sorted(self.listings.values(), key=lambda listing: listing.id)

    def get_listing(self, listing_id: int) -> Optional[Listing]:
        return self.listings.get(listing_id)

    def find_channel_link(self, listing_id: int, channel: Channel) -> Optional[ChannelLink]:
        link_id = self.channel_links_by_listing.get((listing_id, channel))
        if link_id is None:
            return None
        return self.channel_links.get(link_id)

    def upsert_channel_link(self, listing: Listing, channel: Channel, import_url: Optional[str]) -> ChannelLink:
        existing = self.find_channel_link(listing.id, channel)
        if existing:
            existing.import_url = import_url
            return existing
        link_id = self._next_id("channel_link")
        link = ChannelLink.new(link_id, listing_id=listing.id, channel=channel, import_url=import_url)
        listing.channel_links.append(link)
        self.channel_links[link_id] = link
        self.channel_links_by_listing[(listing.id, channel)] = link_id
        self.channel_links_by_token[link.export_token] = link_id
        return link

    def _store_event(self, listing: Listing, event: Event) -> None:
        self.events[event.id] = event
        self.events_by_listing.setdefault(listing.id, []).append(event.id)
        listing.events.append(event)

    def _overlapping_events(self, event: Event) -> List[Event]:
        event_ids = self.events_by_listing.get(event.listing_id, [])
        overlaps: List[Event] = []
        for existing_id in event_ids:
            if existing_id == event.id:
                continue
            other = self.events[existing_id]
            if other.is_shadowed:
                continue
            if other.start_utc < event.end_utc and other.end_utc > event.start_utc:
                overlaps.append(other)
        return overlaps

    def _find_conflict(self, event_a_id: int, event_b_id: int) -> Optional[Conflict]:
        for conflict in self.conflicts.values():
            if conflict.event_ids == {event_a_id, event_b_id}:
                return conflict
        return None

    def _create_conflict(self, listing: Listing, event: Event, other: Event) -> Conflict:
        conflict_id = self._next_id("conflict")
        conflict = Conflict(
            id=conflict_id,
            listing_id=listing.id,
            event_a_id=event.id,
            event_b_id=other.id,
            event_a=event,
            event_b=other,
        )
        self.conflicts[conflict_id] = conflict
        return conflict

    def create_event(
        self,
        listing: Listing,
        *,
        start_utc: datetime,
        end_utc: datetime,
        event_type: EventType,
        source: EventSource,
        summary: Optional[str] = None,
        guest_name: Optional[str] = None,
        external_res_id: Optional[str] = None,
    ) -> tuple[Event, List[Conflict]]:
        event_id = self._next_id("event")
        event = Event(
            id=event_id,
            listing_id=listing.id,
            type=event_type,
            source=source,
            start_utc=start_utc,
            end_utc=end_utc,
            guest_name=guest_name,
            external_res_id=external_res_id,
            summary=summary,
        )
        self._store_event(listing, event)
        conflicts: List[Conflict] = []
        for other in self._overlapping_events(event):
            existing = self._find_conflict(event.id, other.id)
            if existing:
                conflicts.append(existing)
            else:
                conflicts.append(self._create_conflict(listing, event, other))
        return event, conflicts

    def list_events(self, listing: Listing) -> List[Event]:
        return sorted(listing.events, key=lambda event: event.start_utc)

    def list_conflicts(self) -> List[Conflict]:
        return sorted(self.conflicts.values(), key=lambda conflict: conflict.created_at, reverse=True)

    def get_conflict(self, conflict_id: int) -> Optional[Conflict]:
        return self.conflicts.get(conflict_id)

    def resolve_conflict(self, conflict: Conflict, winner_event_id: int, resolution: Optional[str]) -> Conflict:
        if winner_event_id not in conflict.event_ids:
            raise ValueError("Winner must be one of the conflicting events")
        loser_event_id = next(event_id for event_id in conflict.event_ids if event_id != winner_event_id)
        loser_event = self.events.get(loser_event_id)
        if loser_event is None:
            raise ValueError("Loser event missing")
        loser_event.is_shadowed = True
        conflict.status = ConflictStatus.RESOLVED
        conflict.winner_event_id = winner_event_id
        conflict.resolution = resolution
        conflict.resolved_at = datetime.now(timezone.utc)
        return conflict

    def find_channel_link_by_token(self, token: str) -> Optional[ChannelLink]:
        link_id = self.channel_links_by_token.get(token)
        if link_id is None:
            return None
        return self.channel_links.get(link_id)


_DATABASES: Dict[str, Database] = {}


def _database_for_url(url: str) -> Database:
    if url not in _DATABASES:
        _DATABASES[url] = Database()
    return _DATABASES[url]


class Engine:
    def __init__(self, database: Database) -> None:
        self.database = database


def get_database() -> Database:
    return _database_for_url(settings.database_url)


def reset_database() -> None:
    get_database().reset()


class DatabaseSession:
    def __init__(self, database: Database) -> None:
        self._database = database

    def __getattr__(self, item: str):
        return getattr(self._database, item)

    def close(self) -> None:  # pragma: no cover - no resources to release
        pass


engine = Engine(get_database())


def SessionLocal() -> DatabaseSession:
    return DatabaseSession(get_database())


def get_session() -> DatabaseSession:
    return SessionLocal()


from . import models as _models
_models.engine = engine
