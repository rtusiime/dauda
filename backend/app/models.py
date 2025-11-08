from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

class Channel(str, Enum):
    AIRBNB = "AIRBNB"
    BOOKING = "BOOKING"


class EventType(str, Enum):
    RESERVATION = "RESERVATION"
    BLOCK = "BLOCK"


class EventSource(str, Enum):
    AIRBNB = "AIRBNB"
    BOOKING = "BOOKING"
    MANUAL = "MANUAL"


class ConflictStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True


@dataclass
class Listing:
    id: int
    name: str
    timezone: str
    active: bool = True
    channel_links: list["ChannelLink"] = field(default_factory=list)
    events: list["Event"] = field(default_factory=list)


@dataclass
class ChannelLink:
    id: int
    listing_id: int
    channel: Channel
    import_url: Optional[str]
    export_token: str

    @classmethod
    def new(cls, link_id: int, *, listing_id: int, channel: Channel, import_url: Optional[str]) -> "ChannelLink":
        token = secrets.token_urlsafe(32)
        return cls(id=link_id, listing_id=listing_id, channel=channel, import_url=import_url, export_token=token)


@dataclass
class Event:
    id: int
    listing_id: int
    type: EventType
    source: EventSource
    start_utc: datetime
    end_utc: datetime
    guest_name: Optional[str] = None
    external_res_id: Optional[str] = None
    summary: Optional[str] = None
    is_shadowed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Conflict:
    id: int
    listing_id: int
    event_a_id: int
    event_b_id: int
    status: ConflictStatus = ConflictStatus.OPEN
    winner_event_id: Optional[int] = None
    resolution: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    event_a: Optional[Event] = None
    event_b: Optional[Event] = None

    @property
    def event_ids(self) -> set[int]:
        return {self.event_a_id, self.event_b_id}


class _Metadata:
    @staticmethod
    def create_all(bind: object | None = None) -> None:
        from .database import reset_database

        reset_database()

    @staticmethod
    def drop_all(bind: object | None = None) -> None:
        from .database import reset_database

        reset_database()


class _Base:
    metadata = _Metadata()


Base = _Base()

