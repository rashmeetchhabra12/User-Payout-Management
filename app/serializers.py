from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_primitive(value: Any) -> Any:
    if is_dataclass(value):
        return to_primitive(asdict(value))
    if isinstance(value, dict):
        return {key: to_primitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_primitive(item) for item in value]
    if isinstance(value, tuple):
        return [to_primitive(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
