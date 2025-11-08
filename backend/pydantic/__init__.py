from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, TypeVar, get_args, get_origin, get_type_hints


class _Missing:
    pass


MISSING = _Missing()


class FieldInfo:
    def __init__(self, default: Any = MISSING, **metadata: Any) -> None:
        self.default = default
        self.metadata = metadata


def Field(default: Any = MISSING, **metadata: Any) -> FieldInfo:
    return FieldInfo(default=default, **metadata)


T = TypeVar("T", bound="BaseModel")


def _coerce(annotation: Any, value: Any) -> Any:
    if value is None or annotation is Any:
        return value
    origin = get_origin(annotation)
    if origin is None and isinstance(annotation, type):
        if issubclass(annotation, Enum):
            if isinstance(value, annotation):
                return value
            return annotation(value)
        if annotation in {int, float, str, bool}:
            return annotation(value)
        if annotation is datetime and isinstance(value, str):
            return datetime.fromisoformat(value)
        if annotation is date and isinstance(value, str):
            return date.fromisoformat(value)
        if annotation is time and isinstance(value, str):
            return time.fromisoformat(value)
        return value
    if origin in {list, tuple, set}:
        args = get_args(annotation) or (Any,)
        inner = args[0]
        converted = [_coerce(inner, item) for item in value]
        if origin is list:
            return converted
        if origin is tuple:
            return tuple(converted)
        return set(converted)
    if origin is dict:
        key_type, value_type = get_args(annotation) or (Any, Any)
        return {
            _coerce(key_type, key): _coerce(value_type, item)
            for key, item in value.items()
        }
    if origin is not None:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]  # noqa: E721
        if not args:
            return value
        return _coerce(args[0], value)
    return value


class BaseModel:
    def __init__(self, **data: Any) -> None:
        type_hints = get_type_hints(self.__class__)
        for field_name, annotation in type_hints.items():
            default = self._default_for(field_name)
            if field_name in data:
                value = _coerce(annotation, data[field_name])
            elif default is not MISSING:
                if callable(default) and not isinstance(default, FieldInfo):
                    value = default()
                else:
                    value = default
            else:
                value = None
            setattr(self, field_name, value)

    @classmethod
    def _default_for(cls, name: str) -> Any:
        value = getattr(cls, name, MISSING)
        if isinstance(value, FieldInfo):
            if value.default is MISSING:
                return MISSING
            return value.default
        return value

    def model_dump(self) -> dict[str, Any]:
        type_hints = get_type_hints(self.__class__)
        result: dict[str, Any] = {}
        for field_name in type_hints:
            value = getattr(self, field_name)
            result[field_name] = self._serialize(value)
        return result

    @classmethod
    def model_validate(cls: type[T], data: Any) -> T:
        if isinstance(data, cls):
            return data
        if is_dataclass(data):
            payload = asdict(data)
        elif isinstance(data, dict):
            payload = data
        else:
            hints = get_type_hints(cls)
            payload = {name: getattr(data, name) for name in hints}
        return cls(**payload)

    @staticmethod
    def _serialize(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, time):
            return value.isoformat()
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [BaseModel._serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: BaseModel._serialize(item) for key, item in value.items()}
        return value


__all__ = ["BaseModel", "Field"]
