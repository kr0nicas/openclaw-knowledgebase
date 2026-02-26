"""Centralized logging for OpenClaw Knowledgebase.

All modules should use:
    from knowledgebase.log import get_logger
    logger = get_logger(__name__)

Configuration via environment:
    LOG_LEVEL=DEBUG|INFO|WARNING|ERROR  (default: INFO)
    LOG_FORMAT=rich|json|plain          (default: rich)

Rich handler gives colored, readable output for CLI/dev.
JSON format is available for production log aggregation.
Plain falls back to stdlib formatting.
"""

from __future__ import annotations

import logging
import os
import sys

_configured = False


def setup_logging(
    level: str | None = None,
    fmt: str | None = None,
) -> None:
    """Configure the root logger for the knowledgebase package.

    Safe to call multiple times — only configures once unless forced.
    """
    global _configured
    if _configured:
        return
    _configured = True

    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    fmt = (fmt or os.getenv("LOG_FORMAT", "rich")).lower()

    numeric_level = getattr(logging, level, logging.INFO)

    # Get the knowledgebase root logger
    root = logging.getLogger("knowledgebase")
    root.setLevel(numeric_level)

    # Remove any existing handlers (prevents duplicates on reload)
    root.handlers.clear()

    if fmt == "rich":
        try:
            from rich.logging import RichHandler
            handler = RichHandler(
                level=numeric_level,
                show_time=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
                tracebacks_show_locals=numeric_level <= logging.DEBUG,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
        except ImportError:
            # Fallback if rich is somehow not available
            handler = _plain_handler(numeric_level)
    elif fmt == "json":
        handler = _json_handler(numeric_level)
    else:
        handler = _plain_handler(numeric_level)

    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("urllib3", "requests", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _plain_handler(level: int) -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    return handler


def _json_handler(level: int) -> logging.Handler:
    """Simple JSON-lines handler for log aggregation."""
    import json
    from datetime import datetime, timezone

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                **({"exc": self.formatException(record.exc_info)}
                   if record.exc_info else {}),
            })

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    return handler


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the given module name.

    Automatically initializes logging on first call.

    Usage:
        from knowledgebase.log import get_logger
        logger = get_logger(__name__)
        logger.info("Starting process", extra={"source_id": 42})
    """
    setup_logging()
    return logging.getLogger(name)
