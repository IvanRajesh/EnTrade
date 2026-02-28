"""
Logging and notification system for ExitWave.

Provides dual-output logging to both console (with color) and
daily rotating log files.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pytz

IST = pytz.timezone("Asia/Kolkata")


class ISTFormatter(logging.Formatter):
    """Custom formatter that uses IST timezone for all timestamps."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def _enable_ansi_colors():
    """Enable ANSI escape codes on Windows 10+. No-op on Linux/macOS."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


_enable_ansi_colors()


class ConsoleFormatter(ISTFormatter):
    """Colored console output formatter. Disables colors when not a TTY."""

    COLORS = {
        logging.DEBUG: "\033[90m",      # Grey
        logging.INFO: "\033[97m",       # White
        logging.WARNING: "\033[93m",    # Yellow
        logging.ERROR: "\033[91m",      # Red
        logging.CRITICAL: "\033[91;1m", # Bold Red
    }
    RESET = "\033[0m"

    _use_color = sys.stdout.isatty()

    def format(self, record):
        timestamp = self.formatTime(record)
        level = record.levelname.ljust(5)
        message = record.getMessage()
        if self._use_color:
            color = self.COLORS.get(record.levelno, self.RESET)
            return f"{color}[{timestamp}] [{level}] {message}{self.RESET}"
        return f"[{timestamp}] [{level}] {message}"


def setup_logging(log_dir: Path, dry_run: bool = False) -> logging.Logger:
    """
    Configure the ExitWave logger with console + file handlers.

    Args:
        log_dir: Directory for log files.
        dry_run: If True, add [DRY-RUN] prefix to log file name.

    Returns:
        Configured logger instance.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("exitwave")
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler — INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    # File handler — DEBUG and above (daily log file)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    prefix = "dryrun_" if dry_run else ""
    log_file = log_dir / f"exitwave_{prefix}{today}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = ISTFormatter(
        fmt="[%(asctime)s] [%(levelname)-5s] %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the ExitWave logger (must be set up first via setup_logging)."""
    return logging.getLogger("exitwave")
