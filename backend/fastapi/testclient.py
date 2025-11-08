from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Optional

from . import FastAPI
from .responses import PlainTextResponse


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return value


class Response:
    def __init__(self, status_code: int, data: Any, response_class: Optional[type]) -> None:
        self.status_code = status_code
        self._data = data
        self._response_class = response_class
        if (
            isinstance(data, str)
            or response_class is not None
            and getattr(response_class, "media_type", "") != "application/json"
        ):
            self._text = str(data)
            try:
                self._json_data = json.loads(self._text)
            except json.JSONDecodeError:
                self._json_data = None
        else:
            self._json_data = _to_jsonable(data)
            self._text = json.dumps(self._json_data)

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("Response does not contain JSON data")
        return self._json_data

    @property
    def content(self) -> bytes:
        return self._text.encode()


class TestClient:
    __test__ = False

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def request(
        self,
        method: str,
        path: str,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        status_code, payload, response_class = self.app.handle(
            method.upper(), path, json, headers=headers
        )
        return Response(status_code, payload, response_class)

    def get(self, path: str, headers: dict[str, str] | None = None) -> Response:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        return self.request("POST", path, json=json, headers=headers)


__all__ = ["TestClient"]
