"""
News AI Limited - Structlog Configuration

Follows AEGIS project logging standards using structlog with JSON output.
"""
import structlog
import logging
from pythonjsonlogger import jsonlogger
from ..config import get_settings


def configure_logging():
    """Configure structlog and standard logging"""
    settings = get_settings()

    # Standard logging configuration
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.log_format == "json":
        # JSON logging
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter()
        handler.setFormatter(formatter)

        logging.basicConfig(
            level=log_level,
            handlers=[handler],
            format="%(message)s",
        )
    else:
        # Text logging
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    # Structlog configuration
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Get a configured logger instance"""
    return structlog.get_logger(name)
