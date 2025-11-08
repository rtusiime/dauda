# Dauda Channel Manager MVP

This repository contains the foundations of a lightweight channel manager designed for small hospitality operators in East Africa. The focus of the MVP is fast walk-in blocking, iCal based synchronisation between Airbnb and Booking.com, and conflict resolution when overlapping reservations are detected.

## Features

- FastAPI backend with PostgreSQL/SQLite-compatible models for listings, channel links, events, and conflicts.
- Manual walk-in blocks that immediately affect both channel feeds.
- Import endpoint for Airbnb and Booking.com reservations (intended to be called by background importers).
- Conflict detection and resolution workflow that lets staff decide which reservation to keep.
- Signed iCal feeds per channel that merge manual blocks with opposing-channel reservations.

## Getting started

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management

### Installation

```bash
poetry install
```

### Running the API locally

```bash
poetry run uvicorn app.main:app --reload --app-dir backend
```

The API exposes the following key routes:

- `POST /listings` – create a new unit/listing.
- `POST /listings/{listing_id}/blocks` – create a manual walk-in block.
- `POST /listings/{listing_id}/events/imported` – register a reservation pulled from a channel feed.
- `GET /conflicts` – view open and resolved conflicts.
- `POST /conflicts/{id}/resolve` – pick which reservation wins an overlap.
- `GET /ics/{token}.ics` – signed ICS export for a channel link.

### Testing

```bash
poetry run pytest
```

The tests focus on ensuring that manual blocks appear in the Booking.com-facing ICS feed and that conflicts can be resolved with the losing event being shadowed from exports.

## Next steps

- Build background workers that periodically ingest Airbnb/Booking.com ICS feeds.
- Add authentication and role-based permissions for property staff.
- Implement a PWA frontend and WhatsApp bot that interact with the API exposed here.
