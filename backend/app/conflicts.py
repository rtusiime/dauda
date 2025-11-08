from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import Conflict, ConflictStatus, Event


def find_overlapping_events(db: Session, event: Event) -> list[Event]:
    stmt = (
        select(Event)
        .where(
            Event.listing_id == event.listing_id,
            Event.id != event.id,
            Event.is_shadowed.is_(False),
            and_(Event.start_utc < event.end_utc, Event.end_utc > event.start_utc),
        )
    )
    return list(db.scalars(stmt))


def upsert_conflicts(db: Session, event: Event) -> list[Conflict]:
    overlaps = find_overlapping_events(db, event)
    conflicts: list[Conflict] = []
    for other in overlaps:
        # Check if conflict already exists
        stmt = select(Conflict).where(
            Conflict.listing_id == event.listing_id,
            or_(
                and_(Conflict.event_a_id == event.id, Conflict.event_b_id == other.id),
                and_(Conflict.event_a_id == other.id, Conflict.event_b_id == event.id),
            ),
        )
        existing = db.scalars(stmt).first()
        if existing:
            conflicts.append(existing)
            continue

        conflict = Conflict(
            listing_id=event.listing_id,
            event_a_id=event.id,
            event_b_id=other.id,
            status=ConflictStatus.OPEN,
        )
        db.add(conflict)
        conflicts.append(conflict)
    return conflicts


def resolve_conflict(db: Session, conflict: Conflict, winner_event_id: int, resolution: str | None = None) -> Conflict:
    if winner_event_id not in conflict.event_ids:
        raise ValueError("Winner must be one of the conflicting events")

    loser_event_id = next(eid for eid in conflict.event_ids if eid != winner_event_id)
    loser_event = db.get(Event, loser_event_id)
    if loser_event is None:
        raise ValueError("Loser event missing")

    loser_event.is_shadowed = True

    conflict.status = ConflictStatus.RESOLVED
    conflict.winner_event_id = winner_event_id
    conflict.resolution = resolution
    conflict.resolved_at = datetime.now(timezone.utc)
    db.add(loser_event)
    db.add(conflict)
    return conflict
