"""agent/logger.py — Rotating JSON file logger for the VARION agent.

One logger ("varion"), two handlers:
  - RotatingFileHandler → data/agent.log  (5 MB × 3 files, JSON lines)
  - StreamHandler       → stderr          (plain text, for container stdout capture)

JSON line format:
  {"ts":"2026-04-21T10:14:02Z","level":"INFO","thread":"watcher","msg":"..."}
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

_logger: logging.Logger | None = None


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level":  record.levelname,
            "thread": threading.current_thread().name,
            "msg":    record.getMessage(),
        }, ensure_ascii=False)


def setup(store_dir: str, level: str = "INFO") -> logging.Logger:
    global _logger
    agent_dir = os.path.join(store_dir, "agent")
    os.makedirs(agent_dir, exist_ok=True)

    logger = logging.getLogger("varion")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        # File handler — JSON lines, rotated at 5 MB, keeps 3 backups
        fh = RotatingFileHandler(
            os.path.join(agent_dir, "agent.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(_JsonFormatter())
        logger.addHandler(fh)

    _logger = logger
    return logger


def get() -> logging.Logger:
    """Return the configured logger, or a default if setup() hasn't been called."""
    return _logger or logging.getLogger("varion")
