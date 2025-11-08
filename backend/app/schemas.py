from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from .models import Channel, ConflictStatus, EventSource, EventType, UserRole


class ListingBase(BaseModel):
    name: str = Field(..., max_length=100)
    timezone: str = "Africa/Kampala"


class ListingCreate(ListingBase):
    pass


class ListingRead(ListingBase):
    id: int
    active: bool

    class Config:
        from_attributes = True


class ChannelLinkBase(BaseModel):
    channel: Channel
    import_url: Optional[str] = None


class ChannelLinkCreate(ChannelLinkBase):
    pass


class ChannelLinkRead(ChannelLinkBase):
    id: int
    export_token: str

    class Config:
        from_attributes = True


class EventBase(BaseModel):
    start_utc: datetime
    end_utc: datetime
    type: EventType
    source: EventSource
    guest_name: Optional[str] = None
    external_res_id: Optional[str] = None
    summary: Optional[str] = None


class EventRead(EventBase):
    id: int
    listing_id: int
    is_shadowed: bool

    class Config:
        from_attributes = True


class ManualBlockRequest(BaseModel):
    start_date: date
    end_date: date
    note: Optional[str] = None


class ManualBlockResponse(BaseModel):
    event: EventRead
    conflicts: list[int]


class ImportedEventRequest(BaseModel):
    start_utc: datetime
    end_utc: datetime
    source: EventSource
    external_res_id: Optional[str] = None
    summary: Optional[str] = None
    guest_name: Optional[str] = None


class ConflictEvent(BaseModel):
    id: int
    start_utc: datetime
    end_utc: datetime
    source: EventSource
    type: EventType
    summary: Optional[str]
    is_shadowed: bool

    class Config:
        from_attributes = True


class ConflictRead(BaseModel):
    id: int
    listing_id: int
    status: ConflictStatus
    event_a: ConflictEvent
    event_b: ConflictEvent
    winner_event_id: Optional[int]
    resolution: Optional[str]

    class Config:
        from_attributes = True


class ConflictResolutionRequest(BaseModel):
    winner_event_id: int
    resolution: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.STAFF


class UserRead(BaseModel):
    id: int
    email: str
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True
