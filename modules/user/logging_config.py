# -*- coding: utf-8 -*-
"""
用户模块集中式、结构化、滚动日志配置。

设计
------
* **File handler** (`logs/app.log`) 每行输出一个 JSON 对象（机器可读，可直接接入
  Loki / ELK），并按大小滚动、保留可配置份数备份。满足“日志滚动”需求。
* **Console handler** (`stdout`) 输出人类可读格式，便于本地开发与 `docker logs`
  / shell 重定向查看。
* **密钥脱敏过滤器** 擦除意外写入的 `key=value` 格式密钥（password/token/...），
  确保密钥永不落盘——在既有干净调用点之上再做一层纵深防御。
* 所有第三方 logger（uvicorn、sqlalchemy 等）继承这些 root handler。应用关闭
  uvicorn 自带 access 日志，改由请求中间件输出结构化访问日志。

数据库审计（DB-backed，位于 `audit_log`）与这些运维日志相互独立。

在进程启动时调用一次 :func:`setup_logging`；它是幂等的。
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 所有 env 开关在 modules/user/config 中集中读取一次（ARCH-8）。本模块只消费
# 已解析的值，保证单一事实来源。
from modules.user.config import (
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
