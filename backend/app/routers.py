from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .conflicts import resolve_conflict, upsert_conflicts
from .dependencies import get_db
from .ics import build_ics, events_for_channel
from .models import Channel, ChannelLink, Conflict, Event, EventSource, EventType, Listing
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


def _get_listing(db: Session, listing_id: int) -> Listing:
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("/listings", response_model=ListingRead, status_code=201)
def create_listing(payload: ListingCreate, db: Session = Depends(get_db)) -> Listing:
    listing = Listing(name=payload.name, timezone=payload.timezone)
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.get("/listings", response_model=list[ListingRead])
def list_listings(db: Session = Depends(get_db)) -> Sequence[Listing]:
    stmt = select(Listing).order_by(Listing.id)
    return list(db.scalars(stmt))


@router.post(
    "/listings/{listing_id}/channel-links",
    response_model=ChannelLinkRead,
    status_code=201,
)
def upsert_channel_link(
    listing_id: int, payload: ChannelLinkCreate, db: Session = Depends(get_db)
) -> ChannelLink:
    listing = _get_listing(db, listing_id)
    stmt = select(ChannelLink).where(
        ChannelLink.listing_id == listing.id, ChannelLink.channel == payload.channel
    )
    channel_link = db.scalars(stmt).first()
    if channel_link:
        channel_link.import_url = payload.import_url
    else:
        channel_link = ChannelLink(
            listing_id=listing.id,
            channel=payload.channel,
            import_url=payload.import_url,
        )
    db.add(channel_link)
    db.commit()
    db.refresh(channel_link)
    return channel_link


def _create_event(
    db: Session,
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

    event = Event(
        listing_id=listing.id,
        type=event_type,
        source=source,
        start_utc=start_utc,
        end_utc=end_utc,
        summary=summary,
        guest_name=guest_name,
        external_res_id=external_res_id,
    )
    db.add(event)
    db.flush()
    conflicts = upsert_conflicts(db, event)
    db.commit()
    db.refresh(event)
    return event, [conflict.id for conflict in conflicts]


@router.post(
    "/listings/{listing_id}/blocks",
    response_model=ManualBlockResponse,
    status_code=201,
)
def create_manual_block(
    listing_id: int, payload: ManualBlockRequest, db: Session = Depends(get_db)
) -> ManualBlockResponse:
    listing = _get_listing(db, listing_id)
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
    listing_id: int, payload: ImportedEventRequest, db: Session = Depends(get_db)
) -> EventRead:
    listing = _get_listing(db, listing_id)
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
def list_events(listing_id: int, db: Session = Depends(get_db)) -> list[EventRead]:
    listing = _get_listing(db, listing_id)
    stmt = select(Event).where(Event.listing_id == listing.id).order_by(Event.start_utc)
    return [EventRead.model_validate(event) for event in db.scalars(stmt)]


@router.get("/conflicts", response_model=list[ConflictRead])
def get_conflicts(db: Session = Depends(get_db)) -> list[ConflictRead]:
    stmt = select(Conflict).order_by(Conflict.created_at.desc())
    conflicts = db.scalars(stmt).all()
    return [ConflictRead.model_validate(conflict) for conflict in conflicts]


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictRead)
def resolve_conflict_endpoint(
    conflict_id: int, payload: ConflictResolutionRequest, db: Session = Depends(get_db)
) -> ConflictRead:
    conflict = db.get(Conflict, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    try:
        conflict = resolve_conflict(
            db, conflict, winner_event_id=payload.winner_event_id, resolution=payload.resolution
        )
        db.commit()
    except ValueError as exc:  # pragma: no cover - guard clause
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(conflict)
    return ConflictRead.model_validate(conflict)


@router.get("/ics/{token}.ics", response_class=PlainTextResponse)
def download_ics(token: str, db: Session = Depends(get_db)) -> str:
    stmt = select(ChannelLink).where(ChannelLink.export_token == token)
    link = db.scalars(stmt).first()
    if not link:
        raise HTTPException(status_code=404, detail="Calendar not found")

    listing = link.listing
    stmt = select(Event).where(Event.listing_id == listing.id)
    events = list(db.scalars(stmt))
    filtered = events_for_channel(link.channel, events)
    ics_body = build_ics(listing, link.channel, filtered)
    return ics_body
