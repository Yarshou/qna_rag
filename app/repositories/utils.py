import json
from collections.abc import Mapping
from datetime import UTC, datetime

__all__ = [
    "utcnow",
    "serialize_json",
    "deserialize_json",
]


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def serialize_json(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def deserialize_json(payload: str | None) -> dict[str, object] | None:
    if payload is None:
        return None
    return json.loads(payload)
