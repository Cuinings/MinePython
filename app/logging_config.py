# -*- coding: utf-8 -*-
"""
Centralized, structured, rotating logging configuration for the File Server.

Design
------
* **File handler** (`logs/app.log`) emits one JSON object per line (machine
  readable, ready for Loki / ELK) and rotates by size, keeping a configurable
  number of backups. This satisfies the "log rotation" requirement.
* **Console handler** (`stdout`) emits a human-readable format for local dev
  and `docker logs` / shell-redirect convenience.
* A **secret-redaction filter** scrubs accidental `key=value` secret leakage
  (password/token/authorization/api_key/fernet_key/...) so secrets never land
  in any log file — defense in depth on top of the existing clean call sites.
* All third-party loggers (uvicorn, sqlalchemy, ...) keep their default
  `propagate=True` and inherit these root handlers. The app disables uvicorn's
  own access logging and relies on the request middleware for structured
  access logs.

Audit events (DB-backed, in `audit_log`) are intentionally separate from these
operational logs.

Call :func:`setup_logging` exactly once at process startup; it is idempotent.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

# All env knobs are read once, centrally, in app.config (ARCH-8). This module
# only consumes the already-resolved values so there is a single source of truth.
from app.config import (
    LOG_BACKUPS as _LOG_BACKUPS,
    LOG_DIR as _LOG_DIR,
    LOG_FILE_NAME as _LOG_FILE_NAME,
    LOG_LEVEL as _LOG_LEVEL,
    LOG_MAX_BYTES as _LOG_MAX_BYTES,
)

_SETUP_DONE = False

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# Reserved LogRecord attributes that must NOT be copied into the JSON payload
# as custom fields.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg",
    "name", "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName",
}

# Extra fields injected by third-party loggers (notably uvicorn) that are pure
# noise for a structured log sink — dropped from the JSON output.
_SKIP_EXTRA = {"taskName", "color_message", "asctime"}

# Conservative scrubber: redacts `key=value` / `key: value` for known
# secret-like keys. Non-matching messages pass through untouched.
_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|authorization|access[_-]?token|"
    r"refresh[_-]?token|api[_-]?key|apikey|fernet[_-]?key|private[_-]?key|"
    r"session[_-]?token|bearer)\b\s*[=:]\s*\S+",
    re.UNICODE,
)


def _redact(text):
    """Return *text* with secret values replaced by `***`."""
    if not isinstance(text, str):
        return text
    return _SECRET_RE.sub(lambda m: re.sub(r"[=:]\s*\S+$", "=***", m.group(0)), text)


class SecretRedactingFilter(logging.Filter):
    """Redacts secret values from log messages and their arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                k: (_redact(v) if isinstance(v, str) else v) for k, v in record.args.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per log line with standard + caller-supplied extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach any structured "extra" fields the caller passed.
        for key, val in record.__dict__.items():
            if key in _RESERVED or key in _SKIP_EXTRA or key.startswith("_"):
                continue
            payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable console format."""


def setup_logging() -> None:
    """Configure root logging: rotating JSON file + readable console. Idempotent."""
    global _SETUP_DONE
    if _SETUP_DONE:
        return

    level = _LEVELS.get(_LOG_LEVEL, logging.INFO)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / _LOG_FILE_NAME

    root = logging.getLogger()
    root.setLevel(level)
    # Drop any pre-existing handlers (e.g. from a prior basicConfig or re-import).
    for handler in list(root.handlers):
        root.removeHandler(handler)

    redact = SecretRedactingFilter()

    # Console — human readable, for docker / live tail / shell redirect.
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        TextFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    console.addFilter(redact)
    root.addHandler(console)

    # File — rotating JSON lines for shipping & bounded disk usage.
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUPS,
        encoding="utf-8",
        delay=True,  # don't touch disk until the first real log line
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(redact)
    root.addHandler(file_handler)

    # Quiet noisy access logs from third-party loggers unless debugging.
    if level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _SETUP_DONE = True
