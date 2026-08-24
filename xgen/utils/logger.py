"""
xGen Application Logger.
Configures multi-destination logging: colorized console output + rotating file log in %LOCALAPPDATA%/xGen/logs.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_log_dir() -> Path:
    """Return platform-appropriate writable log directory with safe fallbacks."""
    candidates = []
    if os.name == "nt":
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "xGen" / "logs")
        if os.environ.get("APPDATA"):
            candidates.append(Path(os.environ["APPDATA"]) / "xGen" / "logs")
    candidates.append(Path.home() / ".xgen" / "logs")
    candidates.append(Path(__file__).resolve().parent.parent.parent / "logs")

    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = cand / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return cand
        except Exception:
            continue

    fallback = Path(".") / "logs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def setup_logging(level: int = logging.INFO) -> Path:
    """
    Initialize root logging with stdout streamer and rotating file handler.
    Returns path to active log file.
    """
    log_dir = get_log_dir()
    log_file = log_dir / "xgen.log"

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on re-init
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Stream Handler (Safe UTF-8 with fallback on Windows console)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # 2. 5MB Rotating File Handler (3 backups)
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as e:
        root.warning("Could not initialize file logging to %s: %s", log_file, e)

    return log_file
