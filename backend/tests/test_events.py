from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure a dedicated SQLite database file per test session
TEST_DB_PATH = Path("./test_channel_manager.db")
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["CHANNEL_MANAGER_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"  # noqa: E501

from app.database import SessionLocal  # noqa: E402
from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, engine  # noqa: E402


Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_client() -> TestClient:
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def create_listing(client: TestClient, name: str = "Room 1") -> int:
    resp = client.post("/listings", json={"name": name, "timezone": "Africa/Kampala"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def create_channel_link(client: TestClient, listing_id: int, channel: str) -> str:
    resp = client.post(
        f"/listings/{listing_id}/channel-links",
        json={"channel": channel, "import_url": None},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["export_token"]


def test_manual_block_exposed_in_ics() -> None:
    client = create_client()
    listing_id = create_listing(client)
    booking_token = create_channel_link(client, listing_id, "BOOKING")

    payload = {"start_date": "2024-02-10", "end_date": "2024-02-12", "note": "Walk-in"}
    resp = client.post(f"/listings/{listing_id}/blocks", json=payload)
    assert resp.status_code == 201, resp.text

    ics_resp = client.get(f"/ics/{booking_token}.ics")
    assert ics_resp.status_code == 200
    body = ics_resp.text
    assert "SUMMARY:BLOCK" in body
    assert "DTSTART;VALUE=DATE:20240210" in body
    assert "DTEND;VALUE=DATE:20240213" in body


def test_conflict_resolution_shadow_manual_block() -> None:
    client = create_client()
    listing_id = create_listing(client)
    booking_token = create_channel_link(client, listing_id, "BOOKING")

    block_resp = client.post(
        f"/listings/{listing_id}/blocks",
        json={"start_date": "2024-03-10", "end_date": "2024-03-12"},
    )
    assert block_resp.status_code == 201
    block_event_id = block_resp.json()["event"]["id"]

    start_utc = datetime(2024, 3, 11, 12, tzinfo=timezone.utc).isoformat()
    end_utc = datetime(2024, 3, 13, 10, tzinfo=timezone.utc).isoformat()
    import_resp = client.post(
        f"/listings/{listing_id}/events/imported",
        json={
            "start_utc": start_utc,
            "end_utc": end_utc,
            "source": "AIRBNB",
            "summary": "Guest Test",
        },
    )
    assert import_resp.status_code == 201, import_resp.text
    airbnb_event_id = import_resp.json()["id"]

    conflicts_resp = client.get("/conflicts")
    assert conflicts_resp.status_code == 200
    conflicts = conflicts_resp.json()
    assert len(conflicts) == 1
    conflict_id = conflicts[0]["id"]

    resolve_resp = client.post(
        f"/conflicts/{conflict_id}/resolve",
        json={"winner_event_id": airbnb_event_id, "resolution": "Keep Airbnb"},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved_conflict = resolve_resp.json()
    assert resolved_conflict["winner_event_id"] == airbnb_event_id

    events_resp = client.get(f"/listings/{listing_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    shadowed = next(event for event in events if event["id"] == block_event_id)
    assert shadowed["is_shadowed"] is True

    ics_resp = client.get(f"/ics/{booking_token}.ics")
    body = ics_resp.text
    assert "Airbnb Reservation" in body
    # Manual block should not appear after being shadowed
    assert "SUMMARY:BLOCK" not in body

