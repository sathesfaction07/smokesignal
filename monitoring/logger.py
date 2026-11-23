"""
monitoring/logger.py — Structured JSON logging for observability.

Produces structured logs that can be:
  - Shipped to CloudWatch Logs
  - Parsed by CloudWatch Metric Filters
  - Ingested by any log aggregation tool (Splunk, ELK, Grafana Loki)

Log format:
  {"timestamp": ..., "level": ..., "module": ..., "event": ..., "data": {...}}
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "event": record.getMessage(),
        }

        # Attach structured data if provided
        if hasattr(record, "data") and record.data:
            log_entry["data"] = record.data

        # Attach exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure structured JSON logging for the application.

    Returns the root application logger.
    All child loggers (e.g., 'vista.agentcore') inherit this config.
    """
    root_logger = logging.getLogger("vista")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on reload
    root_logger.handlers.clear()

    # JSON handler → stdout (Docker/CloudWatch Logs picks this up)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    return root_logger


def log_event(logger: logging.Logger, event: str, data: dict = None, level: str = "info"):
    """Emit a structured log event with optional data payload."""
    record = logger.makeRecord(
        name=logger.name,
        level=getattr(logging, level.upper(), logging.INFO),
        fn="", lno=0, msg=event, args=(), exc_info=None,
    )
    record.data = data
    logger.handle(record)
