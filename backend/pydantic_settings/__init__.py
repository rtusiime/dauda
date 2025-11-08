from __future__ import annotations

import os
from typing import Any, Dict

from pydantic import BaseModel


class BaseSettings(BaseModel):
    class Config:
        env_prefix = ""
        env_file = None

    def __init__(self, **data: Any) -> None:
        annotations: Dict[str, Any] = getattr(self, "__annotations__", {})
        prefix = getattr(self.Config, "env_prefix", "")
        for field_name in annotations:
            env_key = f"{prefix}{field_name}".upper()
            if env_key in os.environ and field_name not in data:
                data[field_name] = os.environ[env_key]
        super().__init__(**data)


__all__ = ["BaseSettings"]
