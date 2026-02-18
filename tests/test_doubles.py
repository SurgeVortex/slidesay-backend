"""
Test doubles (fakes) for testing with actual implementations.

These are lightweight, in-memory implementations that follow the interfaces
but don't require external dependencies like Cosmos DB or Azure AD.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from src.interfaces.database_interface import IDatabaseService
from src.interfaces.monitoring_interface import IMonitoringService
from src.interfaces.rate_limiter_interface import IRateLimiter

# Exported test doubles for import in tests
__all__ = [
    "InMemoryDatabaseService",
    "FakeMonitoringService",
    "InMemoryRateLimiter",
    "FakeAuthService",
]


# Full-featured FakeAuthService for test_auth.py compatibility
class FakeAuthService:
    def __init__(self, database_service=None):
        self.database_service = database_service
        self._users = {}
        self._valid_tokens = {}
        self._should_fail = False
        self._failure_message = None
        self._last_token = None
        self._return_none_on_validate = False

    class User:
        def __init__(self, user_id, **claims):
            self.id = user_id
            for k, v in claims.items():
                setattr(self, k, v)

    class Result:
        def __init__(
            self, success: bool, user_claims: dict | None = None, error_message: str | None = None
        ) -> None:
            self.success = success
            self.user_claims = user_claims
            self.error_message = error_message

    def add_valid_token(self, token, claims):
        self._valid_tokens[token] = claims

    def set_failure_mode(self, should_fail: bool):
        self._should_fail = should_fail

    def set_return_none_on_validate(self, value: bool):
        self._return_none_on_validate = value

    def set_validation_failure(self, fail: bool, message: str | None = None) -> None:
        self._should_fail = fail
        self._failure_message = message

    async def validate_request(self, req, *args, **kwargs):
        auth_header = req.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return self.Result(
                False, user_claims=None, error_message="Missing or invalid Authorization header"
            )
        token = auth_header[len("Bearer ") :]
        self._last_token = token
        if self._should_fail:
            return self.Result(
                False, user_claims=None, error_message=self._failure_message or "Auth failure"
            )
        claims = self._valid_tokens.get(token)
        if claims is None and self._return_none_on_validate:
            return None
        if claims is None:
            return self.Result(False, user_claims=None, error_message="Invalid token")
        return self.Result(True, user_claims=claims, error_message=None)

    async def get_or_create_user(self, claims, *args, **kwargs):
        # Always return a user object, never None, and sync with database
        user_id = None
        if claims and "sub" in claims:
            user_id = claims["sub"]
        if not user_id:
            user_id = "test-user"

        # Check if user exists in database (only if database service is set)
        if self.database_service is not None:
            db_user = await self.database_service.get_user_by_id(user_id)
            if db_user is not None:
                # Update _users cache if needed
                if user_id not in self._users:
                    self._users[user_id] = self.User(user_id, **db_user)
                return self._users[user_id], False

        # Create new user
        user = self.User(user_id, **(claims or {}))
        self._users[user_id] = user
        # Persist to database if service is available
        if self.database_service is not None:
            await self.database_service.create_user({"id": user_id, **(claims or {})})
        return user, True

    async def validate_token(self, token, *args, **kwargs):
        if self._should_fail:
            return None
        return self._valid_tokens.get(token)


class InMemoryDatabaseService(IDatabaseService):
    """In-memory database implementation for testing."""

    def __init__(self):
        self._users: dict[str, dict[str, Any]] = {}
        self._audit_logs: list[dict[str, Any]] = []
        self._initialized = False
        self._operation_count = 0
        self._error_count = 0
        self._should_fail = False  # For testing error handling
        self._closed = False

    async def initialize(self) -> None:
        """Initialize in-memory storage."""
        self._initialized = True

    async def health_check(self) -> bool:
        """Check if initialized."""
        return self._initialized and not self._closed

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create user with automatic field generation."""
        # Add createdAt if missing (real business logic)
        if "createdAt" not in user_data:
            user_data["createdAt"] = datetime.now(UTC).isoformat()

        # Ensure userId matches id (partition key logic)
        if "userId" not in user_data and "id" in user_data:
            user_data["userId"] = user_data["id"]

        user_id = user_data.get("id") or user_data.get("userId")
        if not user_id:
            return None

        self._users[user_id] = user_data.copy()
        return user_data

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Get user by ID."""
        return self._users.get(user_id)

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update user with merge logic."""
        existing = self._users.get(user_id)
        if not existing:
            return None

        # Merge updates with existing data (real business logic)
        updated = {**existing, **updates}
        self._users[user_id] = updated
        return updated

    async def delete_user(self, user_id: str) -> bool:
        """Soft delete user."""
        if user_id in self._users:
            self._users[user_id]["isActive"] = False
            return True
        return False

    async def create_audit_log(self, audit_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create audit log with automatic field generation."""
        # Simulate failure if requested
        if self._should_fail:
            raise Exception("Simulated database error")

        # Generate ID if missing (real business logic)
        if "id" not in audit_data:
            audit_data["id"] = str(uuid.uuid4())

        # Add timestamp if missing (real business logic)
        if "timestamp" not in audit_data:
            audit_data["timestamp"] = datetime.now(UTC).isoformat()

        # Add date partition key (YYYY-MM-DD format) - real business logic
        if "date" not in audit_data:
            audit_data["date"] = datetime.now(UTC).strftime("%Y-%m-%d")

        # Add TTL for automatic deletion after 30 days (real business logic)
        if "ttl" not in audit_data:
            audit_data["ttl"] = 2592000  # 30 days in seconds

        # Initialize metadata dict if missing (real business logic)
        if "metadata" not in audit_data:
            audit_data["metadata"] = {}

        # Validate required fields (real business logic)
        if "userId" not in audit_data:
            raise ValueError("userId is required for audit log")
        if "action" not in audit_data:
            raise ValueError("action is required for audit log")

        self._audit_logs.append(audit_data.copy())
        return audit_data

    async def get_audit_logs(
        self, user_id: str, limit: int = 50, days: int = 7
    ) -> list[dict[str, Any]]:
        """Get audit logs for user, sorted by timestamp descending."""
        # Filter by userId (cross-partition query simulation)
        user_logs = [log for log in self._audit_logs if log.get("userId") == user_id]

        # Sort by timestamp descending (real business logic)
        user_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Apply limit
        return user_logs[:limit]

    async def query_items(
        self,
        container_name: str,
        query: str,
        parameters: list[dict[str, Any]] | None = None,
        partition_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Simple query implementation."""
        # For testing, just return empty list
        return []

    def get_container_client(self, container_name: str):
        """Return mock container client."""
        return None

    async def close(self) -> None:
        """Close connections."""
        self._closed = True


class FakeMonitoringService(IMonitoringService):
    """Fake monitoring service that tracks calls without external dependencies."""

    def __init__(self):
        self.spans: list[dict[str, Any]] = []
        self.metrics: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.current_trace_id: str | None = None
        self.request_start_time: float | None = None

    def start_request(self):
        """Start request timing."""
        import time

        self.request_start_time = time.time()

        # Generate trace ID (real business logic)
        import secrets

        self.current_trace_id = secrets.token_hex(16)

    def get_trace_id(self) -> str:
        """Get current trace ID in 032x format."""
        if not self.current_trace_id:
            import secrets

            self.current_trace_id = secrets.token_hex(16)
        return self.current_trace_id

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logs.append(
            {"level": "info", "message": message, "trace_id": self.current_trace_id, **kwargs}
        )

    def log_info(self, message: str, labels: dict[str, str] | None = None, **kwargs: Any) -> None:
        """Alias for info."""
        self.info(message, labels=labels, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logs.append(
            {"level": "warning", "message": message, "trace_id": self.current_trace_id, **kwargs}
        )

    def log_warning(
        self, message: str, labels: dict[str, str] | None = None, **kwargs: Any
    ) -> None:
        """Alias for warning."""
        self.warning(message, labels=labels, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logs.append(
            {"level": "error", "message": message, "trace_id": self.current_trace_id, **kwargs}
        )

    def log_error(self, message: str, labels: dict[str, str] | None = None, **kwargs: Any) -> None:
        """Alias for error."""
        self.error(message, labels=labels, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logs.append(
            {"level": "debug", "message": message, "trace_id": self.current_trace_id, **kwargs}
        )

    def log_debug(self, message: str, **kwargs):
        """Alias for debug."""
        self.debug(message, **kwargs)

    def record_request(
        self, route: str, method: str, status_code: int, duration_ms: float | None = None
    ):
        """Record HTTP request metrics."""
        self.metrics.append(
            {
                "type": "http_request",
                "route": route,
                "method": method,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
        )

        # Record error if status >= 400
        if status_code >= 400:
            self.metrics.append(
                {"type": "http_error", "route": route, "method": method, "status_code": status_code}
            )

    def record_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a custom metric."""
        self.metrics.append(
            {"type": "custom_metric", "name": name, "value": value, "labels": labels or {}}
        )

    def record_database_operation(self, operation: str, duration_ms: float, success: bool = True):
        """Record database operation metrics."""
        self.metrics.append(
            {
                "type": "database_operation",
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
            }
        )

    def record_auth_event(self, event_type: str, success: bool, user_id: str | None = None) -> None:
        """Record authentication event."""
        self.metrics.append(
            {"type": "auth_event", "event_type": event_type, "success": success, "user_id": user_id}
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
        """Create audit log with trace correlation."""
        audit_log = {
            "userId": user_id,
            "action": action,
            "resource": resource,
            "method": method,
            "statusCode": status_code,
            "timestamp": datetime.now(UTC).isoformat(),
            "traceId": self.get_trace_id(),  # Trace correlation
            "ipAddress": ip_address,
            "userAgent": user_agent,
            "metadata": metadata or {},
        }
        self.audit_logs.append(audit_log)
        return True


class InMemoryRateLimiter(IRateLimiter):
    """In-memory rate limiter for testing."""

    def __init__(self):
        self._limits: dict[str, dict[str, Any]] = {}
        self._requests: dict[str, list[float]] = {}

    def set_limit(self, key: str, max_requests: int, window_seconds: int):
        """Configure rate limit for a key."""
        self._limits[key] = {"max_requests": max_requests, "window_seconds": window_seconds}

    async def check_rate_limit(
        self,
        req,  # azure.functions.HttpRequest
        user_id: str | None = None,
        endpoint: str | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Check rate limit using Azure Functions request."""
        # Extract key from request
        key = req.headers.get("X-Forwarded-For", "default")
        return await self.check_rate_limit_by_key(key, user_id, endpoint)

    async def check_rate_limit_by_key(
        self, key: str, user_id: str | None = None, endpoint: str | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Check if request is within rate limits."""
        import time

        now = time.time()

        # Get configured limit or use defaults
        max_requests = 100
        window_seconds = 60

        if key in self._limits:
            max_requests = self._limits[key]["max_requests"]
            window_seconds = self._limits[key]["window_seconds"]

        # Initialize request list for key
        if key not in self._requests:
            self._requests[key] = []

        # Remove old requests outside window
        window_start = now - window_seconds
        self._requests[key] = [
            req_time for req_time in self._requests[key] if req_time > window_start
        ]

        # Check if limit exceeded
        current_count = len(self._requests[key])
        is_allowed = current_count < max_requests

        if is_allowed:
            # Add this request
            self._requests[key].append(now)

        rate_limit_info = {
            "limit": max_requests,
            "remaining": max(0, max_requests - current_count - (1 if is_allowed else 0)),
            "reset_time": int(now + window_seconds),
        }

        return (is_allowed, rate_limit_info)

    def create_rate_limit_response(self, rate_limit_info: dict):
        """Create HTTP 429 response."""
        import json

        import azure.functions as func

        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Rate limit exceeded",
                    "limit": rate_limit_info["limit"],
                    "reset_time": rate_limit_info["reset_time"],
                }
            ),
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(rate_limit_info["limit"]),
                "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
                "X-RateLimit-Reset": str(rate_limit_info["reset_time"]),
            },
        )

    def add_rate_limit_headers(self, response, rate_limit_info: dict | None):
        """Add rate limit headers to response."""
        if not rate_limit_info:
            return response

        # For test double, just return response as-is
        return response
