"""
Monitoring Service Interface.

Defines the contract for monitoring services.
"""

from abc import ABC, abstractmethod
from typing import Any


class IMonitoringService(ABC):
    """Interface for monitoring services."""

    @abstractmethod
    def start_request(self) -> None:
        """Start monitoring a request."""
        pass

    @abstractmethod
    def log_info(self, message: str, labels: dict[str, str] | None = None, **fields: Any) -> None:
        """Log info message."""
        pass

    @abstractmethod
    def log_warning(
        self, message: str, labels: dict[str, str] | None = None, **fields: Any
    ) -> None:
        """Log warning message."""
        pass

    @abstractmethod
    def log_error(self, message: str, labels: dict[str, str] | None = None, **fields: Any) -> None:
        """Log error message."""
        pass

    @abstractmethod
    def record_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a metric."""
        pass

    @abstractmethod
    def record_request(
        self, endpoint: str, method: str, status_code: int, duration_ms: float | None = None
    ) -> None:
        """Record HTTP request."""
        pass

    @abstractmethod
    def record_auth_event(self, event_type: str, success: bool, user_id: str | None = None) -> None:
        """Record authentication event."""
        pass

    @abstractmethod
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
        """
        Create audit log entry in database.
        Args:
            user_id: User who performed the action
            action: Action type (e.g., "login", "update_profile")
            resource: Resource path (e.g., "/api/user/profile")
            method: HTTP method (GET, POST, etc.)
            status_code: Response status code
            ip_address: Client IP address
            user_agent: Client user agent string
            metadata: Additional context
        Returns:
            True if audit log created successfully
        """
        pass

    @abstractmethod
    def get_trace_id(self) -> str | None:
        """Get current OpenTelemetry trace ID for correlation."""
        pass
