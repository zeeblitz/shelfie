"""Structured logging configuration for Shelfie bot."""

import logging

import structlog

# Get logger
logger = structlog.get_logger()

# Set log level from settings
def configure_logging(level: str = "INFO") -> None:
    """Configure logging level based on settings."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=log_level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

# Example usage in services
def log_message(message: str, **kwargs) -> None:
    """Log a message with structured data."""
    logger.info(message, **kwargs)
