from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


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


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    timezone = Column(String(64), nullable=False, default="Africa/Kampala")
    active = Column(Boolean, default=True, nullable=False)

    channel_links = relationship("ChannelLink", back_populates="listing", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="listing", cascade="all, delete-orphan")


class ChannelLink(Base):
    __tablename__ = "channel_links"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False, index=True)
    channel = Column(SAEnum(Channel), nullable=False)
    import_url = Column(Text, nullable=True)
    export_token = Column(String(64), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(32))

    listing = relationship("Listing", back_populates="channel_links")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False, index=True)
    type = Column(SAEnum(EventType), nullable=False)
    source = Column(SAEnum(EventSource), nullable=False)
    start_utc = Column(DateTime(timezone=True), nullable=False)
    end_utc = Column(DateTime(timezone=True), nullable=False)
    guest_name = Column(String(120), nullable=True)
    external_res_id = Column(String(120), nullable=True)
    summary = Column(String(120), nullable=True)
    is_shadowed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    listing = relationship("Listing", back_populates="events")
    conflicts_a = relationship("Conflict", foreign_keys="Conflict.event_a_id", back_populates="event_a")
    conflicts_b = relationship("Conflict", foreign_keys="Conflict.event_b_id", back_populates="event_b")


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False, index=True)
    event_a_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    event_b_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    status = Column(SAEnum(ConflictStatus), nullable=False, default=ConflictStatus.OPEN)
    winner_event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    resolution = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    event_a = relationship("Event", foreign_keys=[event_a_id], back_populates="conflicts_a")
    event_b = relationship("Event", foreign_keys=[event_b_id], back_populates="conflicts_b")

    @property
    def event_ids(self) -> set[int]:
        return {self.event_a_id, self.event_b_id}
