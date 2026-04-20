from datetime import datetime
from typing import Any

__all__ = ["JsonMap", "parse_datetime", "optional_json_map"]

JsonMap = dict[str, Any]


def parse_datetime(value: datetime | str) -> datetime:
    """Normalize a datetime field from a datetime instance or ISO 8601 string."""

    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def optional_json_map(value: Any) -> JsonMap | None:
    """Return an optional shallow-copied mapping for metadata-like payloads."""

    if value is None:
        return None
    return dict(value)
