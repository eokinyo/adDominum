# utils/logger.py
"""
adDominum — logging setup.

Logs are written to %LOCALAPPDATA%\\adDominum\\logs\\ rather than the project
folder. Two reasons:

  1. OneDrive does not sync it. Logs are disposable runtime state and there is
     no reason to push them to the cloud.
  2. Rotation is enforced. Each file is capped at 2 MB with 3 backups kept,
     so the total on disk can never exceed roughly 8 MB regardless of how
     badly something misbehaves.

Usage is unchanged:

    from utils.logger import setup_logging
    logger = setup_logging("main")
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---------------------------------------------------------------
# Where logs live
# ---------------------------------------------------------------
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "adDominum" / "logs"

MAX_BYTES = 2_000_000   # 2 MB per file
BACKUP_COUNT = 3        # keep 3 rolled files -> ~8 MB ceiling

_FORMAT = "%(asctime)s | %(name)-12s | %(levelname)-7s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(name: str = "adDominum", level: int = logging.INFO) -> logging.Logger:
    """
    Return a configured logger.

    Safe to call more than once with the same name — handlers are only
    attached on first call, so repeated calls will not duplicate output.
    """
    logger = logging.getLogger(name)

    # Already configured, hand back the same logger untouched.
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # --- Rotating file handler -----------------------------------
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_DIR / "automation.log",
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError as exc:
        # If the log directory is unavailable, carry on with console only
        # rather than taking the whole run down.
        print(f"[logger] Could not open log file: {exc}", file=sys.stderr)

    # --- Console handler -----------------------------------------
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)
    logger.addHandler(console)

    return logger


def log_location() -> Path:
    """Return the directory logs are being written to (handy for diagnostics)."""
    return LOG_DIR
