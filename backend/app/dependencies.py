from __future__ import annotations

from collections.abc import Generator

from .database import DatabaseSession, get_session


def get_db() -> Generator[DatabaseSession, None, None]:
    db = get_session()
    try:
        yield db
    finally:
        db.close()
