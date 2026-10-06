"""
src/logging_config.py — Application-wide logging setup.

Provides a consistent log format across all modules:
  timestamp | level | module | message

NEVER logs credentials, API keys, or passwords.
"""

import logging
import sys
from src.config import get_config


def setup_logging() -> None:
    """Configure the root logger with a standardised format."""
    config = get_config()
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    # Avoid adding duplicate handlers on repeated calls
    if not root_logger.handlers:
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    for noisy in ("boto3", "botocore", "s3transfer", "urllib3", "httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name, ensuring setup has run."""
    setup_logging()
    return logging.getLogger(name)
