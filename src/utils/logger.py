"""
Structured Logging Setup

Configures structured logging with proper formatting and context.
"""

import logging
import sys
from datetime import UTC, datetime
from typing import Any, cast

import structlog

from src.utils.config import Config


def configure_logging(config: Config | None = None) -> None:
    """Configure structured logging for the application."""
    if config is None:
        config = Config()

    log_level_str = config.get("LOG_LEVEL", "INFO")
    log_level = log_level_str.upper() if log_level_str else "INFO"

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level, logging.INFO),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            add_app_context,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def add_app_context(
    logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Add application context to log entries."""
    config = Config()

    event_dict.setdefault("app", config.get("APP_NAME", "saas-backend"))
    event_dict.setdefault("version", config.get("APP_VERSION", "1.0.0"))
    event_dict.setdefault("environment", config.get("ENVIRONMENT", "unknown"))

    return event_dict


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def log_function_call(
    func_name: str, args: dict[str, Any], duration_ms: float | None = None
) -> None:
    """Log function call with timing information."""
    logger = get_logger("function_calls")

    log_data: dict[str, Any] = {"function": func_name, "args": args}

    if duration_ms is not None:
        log_data["duration_ms"] = duration_ms

    logger.info("function_called", **log_data)


def log_api_request(
    method: str, path: str, status_code: int, duration_ms: float, user_id: str | None = None
) -> None:
    """Log API request with standard fields."""
    logger = get_logger("api_requests")

    log_data: dict[str, Any] = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }

    if user_id:
        log_data["user_id"] = user_id

    logger.info("api_request", **log_data)


def log_database_operation(
    operation: str,
    collection: str,
    duration_ms: float,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Log database operation with timing."""
    logger = get_logger("database")

    log_data: dict[str, Any] = {
        "operation": operation,
        "collection": collection,
        "duration_ms": duration_ms,
        "success": success,
    }

    if error:
        log_data["error"] = error

    if success:
        logger.info("database_operation", **log_data)
    else:
        logger.error("database_operation_failed", **log_data)


def log_security_event(
    event_type: str,
    user_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log security-related events."""
    logger = get_logger("security")

    log_data: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if user_id:
        log_data["user_id"] = user_id

    if ip_address:
        log_data["ip_address"] = ip_address

    if details:
        log_data.update(details)

    logger.warning("security_event", **log_data)


# Initialize logging on module import
configure_logging()
