from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class SafeJsonFormatter(logging.Formatter):
    """Minimal structured log formatter; request bodies/headers are never serialized."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_structured_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
