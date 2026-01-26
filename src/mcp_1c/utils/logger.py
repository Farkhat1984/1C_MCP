"""
Logging configuration for MCP-1C.

Provides structured logging with configurable levels and formats.
"""

import logging
import sys
from typing import Literal

# Module-level logger cache
_loggers: dict[str, logging.Logger] = {}


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    format_string: str | None = None,
) -> None:
    """
    Configure root logger for the application.

    Args:
        level: Logging level
        format_string: Custom format string (optional)
    """
    if format_string is None:
        format_string = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"

    logging.basicConfig(
        level=getattr(logging, level),
        format=format_string,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Uses caching to avoid creating duplicate loggers.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    if name not in _loggers:
        logger = logging.getLogger(name)
        _loggers[name] = logger
    return _loggers[name]
