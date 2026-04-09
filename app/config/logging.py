import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

__all__ = ["StructuredJsonFormatter", "configure_logging"]

_RESERVED_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


class StructuredJsonFormatter(logging.Formatter):
    """Serialize log records into compact JSON for downstream parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install a single root handler with a structured formatter."""

    root_logger = logging.getLogger()
    if any(getattr(handler, "_qna_structured_handler", False) for handler in root_logger.handlers):
        root_logger.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    handler._qna_structured_handler = True  # type: ignore[attr-defined]

    root_logger.addHandler(handler)
    root_logger.setLevel(level)
