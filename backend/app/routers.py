from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from .database import DatabaseSession
from .dependencies import get_db
from .ics import build_ics, events_for_channel
from .models import EventSource, EventType, Listing
from .schemas import (
    ChannelLinkCreate,
    ChannelLinkRead,
    ConflictRead,
    ConflictResolutionRequest,
    EventRead,
    ImportedEventRequest,
    ListingCreate,
    ListingRead,
    ManualBlockRequest,
    ManualBlockResponse,
)

router = APIRouter()


def _ensure_listing(db: DatabaseSession, listing_id: int) -> Listing:
    listing = db.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


def _create_event(
    db: DatabaseSession,
    listing: Listing,
    *,
    start_utc: datetime,
    end_utc: datetime,
    event_type: EventType,
    source: EventSource,
    summary: str | None = None,
    guest_name: str | None = None,
    external_res_id: str | None = None,
) -> tuple[Event, list[int]]:
    if end_utc <= start_utc:
        raise HTTPException(status_code=400, detail="end_utc must be after start_utc")
    event, conflicts = db.create_event(
        listing,
        start_utc=start_utc,
        end_utc=end_utc,
        event_type=event_type,
        source=source,
        summary=summary,
        guest_name=guest_name,
        external_res_id=external_res_id,
    )
    return event, [conflict.id for conflict in conflicts]


@router.post("/listings", response_model=ListingRead, status_code=201)
def create_listing(payload: ListingCreate, db: DatabaseSession = Depends(get_db)) -> ListingRead:
    listing = db.create_listing(payload.name, payload.timezone)
    return ListingRead.model_validate(listing)


@router.get("/listings", response_model=list[ListingRead])
def list_listings(db: DatabaseSession = Depends(get_db)) -> Sequence[ListingRead]:
    return [ListingRead.model_validate(listing) for listing in db.list_listings()]


@router.post(
    "/listings/{listing_id}/channel-links",
    response_model=ChannelLinkRead,
    status_code=201,
)
def upsert_channel_link(
    listing_id: int, payload: ChannelLinkCreate, db: DatabaseSession = Depends(get_db)
) -> ChannelLinkRead:
    listing = _ensure_listing(db, listing_id)
    channel_link = db.upsert_channel_link(listing, payload.channel, payload.import_url)
    return ChannelLinkRead.model_validate(channel_link)


@router.post(
    "/listings/{listing_id}/blocks",
    response_model=ManualBlockResponse,
    status_code=201,
)
def create_manual_block(
    listing_id: int, payload: ManualBlockRequest, db: DatabaseSession = Depends(get_db)
) -> ManualBlockResponse:
    listing = _ensure_listing(db, listing_id)
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    tz = ZoneInfo(listing.timezone)
    start_local = datetime.combine(payload.start_date, time(0, 0), tzinfo=tz)
    end_local = datetime.combine(payload.end_date + timedelta(days=1), time(0, 0), tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    event, conflicts = _create_event(
        db,
        listing,
        start_utc=start_utc,
        end_utc=end_utc,
        event_type=EventType.BLOCK,
        source=EventSource.MANUAL,
        summary=payload.note,
    )
    return ManualBlockResponse(event=EventRead.model_validate(event), conflicts=conflicts)


@router.post(
    "/listings/{listing_id}/events/imported",
    response_model=EventRead,
    status_code=201,
)
def register_imported_event(
    listing_id: int, payload: ImportedEventRequest, db: DatabaseSession = Depends(get_db)
) -> EventRead:
    listing = _ensure_listing(db, listing_id)
    if payload.source not in {EventSource.AIRBNB, EventSource.BOOKING}:
        raise HTTPException(status_code=400, detail="Imported events must originate from a channel")
    event, _ = _create_event(
        db,
        listing,
        start_utc=payload.start_utc,
        end_utc=payload.end_utc,
        event_type=EventType.RESERVATION,
        source=payload.source,
        summary=payload.summary,
        guest_name=payload.guest_name,
        external_res_id=payload.external_res_id,
    )
    return EventRead.model_validate(event)


@router.get("/listings/{listing_id}/events", response_model=list[EventRead])
def list_events(listing_id: int, db: DatabaseSession = Depends(get_db)) -> list[EventRead]:
    listing = _ensure_listing(db, listing_id)
    events = db.list_events(listing)
    return [EventRead.model_validate(event) for event in events]


@router.get("/conflicts", response_model=list[ConflictRead])
def get_conflicts(db: DatabaseSession = Depends(get_db)) -> list[ConflictRead]:
    conflicts = db.list_conflicts()
    return [ConflictRead.model_validate(conflict) for conflict in conflicts]


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictRead)
def resolve_conflict_endpoint(
    conflict_id: int, payload: ConflictResolutionRequest, db: DatabaseSession = Depends(get_db)
) -> ConflictRead:
    conflict = db.get_conflict(conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    try:
        resolved = db.resolve_conflict(conflict, payload.winner_event_id, payload.resolution)
    except ValueError as exc:  # pragma: no cover - guard clause
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConflictRead.model_validate(resolved)


@router.get("/ics/{token}.ics", response_class=PlainTextResponse)
def download_ics(token: str, db: DatabaseSession = Depends(get_db)) -> str:
    link = db.find_channel_link_by_token(token)
    if link is None:
        raise HTTPException(status_code=404, detail="Calendar not found")
    listing = db.get_listing(link.listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    events = db.list_events(listing)
    filtered = events_for_channel(link.channel, events)
    return build_ics(listing, link.channel, filtered)
