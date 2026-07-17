"""Logging setup for Kits Direct Print Agent."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".kits_direct_print_agent" / "logs"
LOG_FILE = LOG_DIR / "agent.log"


def get_logger(name: str = "kits_direct_print") -> logging.Logger:
    """Return a configured logger with rotating file + console handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        # already configured, avoid duplicate handlers
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def tail_log(max_lines: int = 400) -> str:
    """Returns the last `max_lines` lines of the current log file as text,
    for display in the GUI's Logs tab. Returns an empty string if the log
    file does not exist yet.
    """
    if not LOG_FILE.exists():
        return ""
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except OSError:
        return ""