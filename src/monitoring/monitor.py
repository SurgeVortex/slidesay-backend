"""
Monitoring implementation using OpenTelemetry metrics and structured logging.

This module provides a request-scoped monitoring helper that records
basic Golden Signal metrics and writes structured logs with trace
correlation. It intentionally keeps runtime logic simple and uses
typing `cast` for the metric attribute maps because the OpenTelemetry
API expects Mapping[str, Any] at runtime.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from opentelemetry import metrics, trace

from src.interfaces.database_interface import IDatabaseService
from src.interfaces.monitoring_interface import IMonitoringService
from src.utils.logger import get_logger


class MonitoringService(IMonitoringService):
    """Request-scoped monitoring service using OpenTelemetry.

    It provides helpers to record requests, database operations and
    simple auth events. Metrics attribute maps are cast to Mapping to
    satisfy static typing while keeping runtime behavior intact.
    """

    def __init__(self, database_service: IDatabaseService | None = None) -> None:
        self.logger = get_logger(__name__)
        self.database_service = database_service

        self.tracer = trace.get_tracer(__name__)
        self.meter = metrics.get_meter(__name__)

        self.request_start_time: float | None = None

        # Instruments
        self._http_request_counter = self.meter.create_counter(
            name="http.server.requests", description="Total HTTP requests"
        )
        self._http_request_duration = self.meter.create_histogram(
            name="http.server.duration", description="HTTP request duration (ms)"
        )
        self._http_error_counter = self.meter.create_counter(name="http.server.errors")
        self._auth_event_counter = self.meter.create_counter(name="auth.events")
        self._db_operation_counter = self.meter.create_counter(name="db.operations")
        self._db_operation_duration = self.meter.create_histogram(name="db.operation.duration")

    def start_request(self) -> None:
        """Mark the start of a request for duration calculation."""
        self.request_start_time = time.time()

    def log_info(
        self, message: str, labels: Mapping[str, str] | None = None, **fields: Any
    ) -> None:
        payload = {**(dict(labels or {})), **fields}
        trace_id = self.get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        self.logger.info(message, **payload)

    def log_warning(
        self, message: str, labels: Mapping[str, str] | None = None, **fields: Any
    ) -> None:
        payload = {**(dict(labels or {})), **fields}
        trace_id = self.get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        self.logger.warning(message, **payload)

    def log_error(
        self, message: str, labels: Mapping[str, str] | None = None, **fields: Any
    ) -> None:
        payload = {**(dict(labels or {})), **fields}
        trace_id = self.get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        self.logger.error(message, **payload)

    def log_debug(
        self, message: str, labels: Mapping[str, str] | None = None, **fields: Any
    ) -> None:
        payload = {**(dict(labels or {})), **fields}
        trace_id = self.get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        self.logger.debug(message, **payload)

    def record_metric(
        self, name: str, value: float, labels: Mapping[str, str] | None = None
    ) -> None:
        # Fall back to logging for ad-hoc metrics in this template
        self.logger.info("custom_metric", metric_name=name, value=value, **(dict(labels or {})))

    def record_request(
        self, endpoint: str, method: str, status_code: int, duration_ms: float | None = None
    ) -> None:
        if duration_ms is None and self.request_start_time is not None:
            duration_ms = (time.time() - self.request_start_time) * 1000

        attributes: Mapping[str, Any] = {
            "http.route": endpoint,
            "http.method": method,
            "http.status_code": status_code,
        }

        # Record traffic
        self._http_request_counter.add(1, cast(Mapping, attributes))

        # Record latency if available
        if duration_ms is not None:
            self._http_request_duration.record(duration_ms, cast(Mapping, attributes))

        # Record errors
        if status_code >= 400:
            self._http_error_counter.add(1, cast(Mapping, attributes))

    def record_database_operation(
        self, operation: str, duration_ms: float, success: bool = True
    ) -> None:
        attributes: Mapping[str, Any] = {"db.operation": operation, "db.success": success}
        self._db_operation_counter.add(1, cast(Mapping, attributes))
        self._db_operation_duration.record(duration_ms, cast(Mapping, attributes))

    def record_auth_event(self, event_type: str, success: bool, user_id: str | None = None) -> None:
        attributes: Mapping[str, Any] = {"auth.event_type": event_type, "auth.success": success}
        self._auth_event_counter.add(1, cast(Mapping, attributes))
        self.log_info(
            f"auth_event_{event_type}",
            event_type=event_type,
            success=success,
            user_id=user_id or "unknown",
        )

    async def create_audit_log(
        self,
        user_id: str,
        action: str,
        resource: str,
        method: str,
        status_code: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self.database_service:
            self.log_warning("Audit logging disabled - no database service")
            return False

        try:
            audit_data = {
                "id": str(uuid.uuid4()),
                "userId": user_id,
                "action": action,
                "resource": resource,
                "method": method,
                "statusCode": status_code,
                "timestamp": datetime.now(UTC).isoformat(),
                "ipAddress": ip_address,
                "userAgent": user_agent,
                "metadata": metadata or {},
                "traceId": self.get_trace_id(),
            }

            result = await self.database_service.create_audit_log(audit_data)
            if result:
                self.log_debug("audit_log_created", audit_id=audit_data["id"], action=action)
                return True
            self.log_warning("audit_log_creation_failed", action=action)
            return False

        except Exception as exc:  # pragma: no cover - best-effort logging
            self.log_error("audit_log_error", error=str(exc), action=action)
            return False

    def get_trace_id(self) -> str | None:
        span = trace.get_current_span()
        if span and span.is_recording():
            trace_id = span.get_span_context().trace_id
            return format(trace_id, "032x")
        return None
