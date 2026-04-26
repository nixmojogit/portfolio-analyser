"""
logger.py
Utility module for structured logging across all layers.
Log level controlled by system.yaml (log_level key).
"""

from __future__ import annotations
import logging
import sys


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track whether root logger has been set up to avoid duplicate handlers
_root_configured = False


def setup_root_logger(log_level: str = "INFO") -> None:
    """
    Configure the root logger with console handler and standard format.
    Called once at application startup in app.py.
    Safe to call multiple times — only configures once.
    Args:
        log_level: logging level string e.g. 'INFO', 'DEBUG', 'WARNING'
    """
    global _root_configured
    if _root_configured:
        return

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid adding duplicate handlers on reload
    if not root.handlers:
        root.addHandler(handler)

    _root_configured = True


def get_logger(name: str, config: dict | None = None) -> logging.Logger:
    """
    Return a configured logger instance for the given module name.
    Log level read from config (system.log_level) or defaults to INFO.
    Args:
        name   : logger name (typically __name__ of calling module)
        config : merged config dict (optional)
    Returns: configured logging.Logger instance
    """
    log_level = "INFO"
    if config and "system" in config:
        log_level = config["system"].get("log_level", "INFO")

    setup_root_logger(log_level)
    return logging.getLogger(name)