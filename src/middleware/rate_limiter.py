"""
Rate Limiting Middleware

Uses Cosmos DB ratelimits container for persistent rate limiting.
Implements fixed window algorithm with automatic TTL-based cleanup.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import azure.functions as func

from src.interfaces.database_interface import IDatabaseService
from src.interfaces.rate_limiter_interface import IRateLimiter
from src.utils.logger import get_logger


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_window: int
    window_seconds: int

    @property
    def ttl(self) -> int:
        """TTL for rate limit documents (1.5x window to handle overlap)."""
        return int(self.window_seconds * 1.5)


# Default rate limit tiers
DEFAULT_LIMITS = {
    "anonymous": RateLimitConfig(requests_per_window=20, window_seconds=60),  # 20 req/min
    "authenticated": RateLimitConfig(requests_per_window=100, window_seconds=60),  # 100 req/min
    "auth_endpoint": RateLimitConfig(
        requests_per_window=10, window_seconds=60
    ),  # 10 req/min for login
}


class RateLimiter(IRateLimiter):
    """
    Cosmos DB-backed rate limiter using fixed window algorithm.
    Features:
    - Persistent across function invocations (stateless-friendly)
    - Automatic cleanup via TTL
    - Per-user and per-IP limiting
    - Configurable limits per endpoint
    """

    def __init__(self, database_service: IDatabaseService):
        self.logger = get_logger(__name__)
        self.database_service = database_service

    async def check_rate_limit(
        self, req: func.HttpRequest, user_id: str | None = None, endpoint: str | None = None
    ) -> tuple[bool, dict | None]:
        """
        Check if request is within rate limits.
        Args:
            req: Azure Function HTTP request
            user_id: Authenticated user ID (if available)
            endpoint: Endpoint path for specific limits
        Returns:
            Tuple of (is_allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_time
        """
        try:
            await self.database_service.initialize()

            # Determine rate limit key and config
            key, limit_config = self._get_rate_limit_key_and_config(req, user_id, endpoint)

            # Get current window start time
            now = datetime.now(UTC)
            window_start = self._get_window_start(now, limit_config.window_seconds)
            window_id = window_start.strftime("%Y%m%d%H%M%S")

            # Document ID combines key and window
            doc_id = f"{key}_{window_id}"

            # Try to get or create rate limit document
            container = self.database_service.get_container_client("ratelimits")
            if not container:
                self.logger.warning("Rate limits container not initialized, allowing request")
                return True, None

            try:
                # Try to read existing document
                doc = container.read_item(item=doc_id, partition_key=key)
                current_count = doc.get("count", 0)

                # Check if limit exceeded
                if current_count >= limit_config.requests_per_window:
                    self.logger.warning(
                        "Rate limit exceeded",
                        key=key,
                        count=current_count,
                        limit=limit_config.requests_per_window,
                    )

                    reset_time = window_start.timestamp() + limit_config.window_seconds

                    return False, {
                        "limit": limit_config.requests_per_window,
                        "remaining": 0,
                        "reset": int(reset_time),
                        "retry_after": int(reset_time - now.timestamp()),
                    }

                # Increment counter
                doc["count"] = current_count + 1
                doc["lastRequest"] = now.isoformat()
                container.replace_item(item=doc_id, body=doc)

                remaining = limit_config.requests_per_window - doc["count"]
                reset_time = window_start.timestamp() + limit_config.window_seconds

                return True, {
                    "limit": limit_config.requests_per_window,
                    "remaining": remaining,
                    "reset": int(reset_time),
                }

            except Exception:
                # Document doesn't exist, create it
                doc = {
                    "id": doc_id,
                    "key": key,
                    "count": 1,
                    "windowStart": window_start.isoformat(),
                    "limit": limit_config.requests_per_window,
                    "ttl": limit_config.ttl,
                    "firstRequest": now.isoformat(),
                    "lastRequest": now.isoformat(),
                }

                container.create_item(body=doc)

                reset_time = window_start.timestamp() + limit_config.window_seconds

                return True, {
                    "limit": limit_config.requests_per_window,
                    "remaining": limit_config.requests_per_window - 1,
                    "reset": int(reset_time),
                }

        except Exception as e:
            self.logger.error("Rate limit check failed", error=str(e), key=key)
            # Fail open - allow request if rate limiting fails
            return True, None

    def _get_rate_limit_key_and_config(
        self, req: func.HttpRequest, user_id: str | None, endpoint: str | None
    ) -> tuple[str, RateLimitConfig]:
        """Determine rate limit key and configuration."""

        # Special limits for auth endpoints
        if endpoint and "auth" in endpoint:
            ip_address = self._get_client_ip(req)
            return f"ip:{ip_address}:auth", DEFAULT_LIMITS["auth_endpoint"]

        # Authenticated users get higher limits
        if user_id:
            return f"user:{user_id}", DEFAULT_LIMITS["authenticated"]

        # Anonymous requests limited by IP
        ip_address = self._get_client_ip(req)
        return f"ip:{ip_address}", DEFAULT_LIMITS["anonymous"]

    def _get_client_ip(self, req: func.HttpRequest) -> str:
        """Extract client IP address from request."""
        # Check X-Forwarded-For header (set by Azure Front Door / App Gateway)
        forwarded_for = req.headers.get("X-Forwarded-For")
        if forwarded_for:
            # First IP in chain is the original client
            return str(forwarded_for).split(",")[0].strip()

        # Fallback to X-Real-IP
        real_ip = req.headers.get("X-Real-IP")
        if real_ip:
            return str(real_ip)

        # Last resort - use client host (may be Azure infrastructure IP)
        return str(req.headers.get("X-Client-IP") or "unknown")

    def _get_window_start(self, now: datetime, window_seconds: int) -> datetime:
        """Calculate the start of the current fixed window."""
        timestamp = int(now.timestamp())
        window_start_timestamp = (timestamp // window_seconds) * window_seconds
        return datetime.fromtimestamp(window_start_timestamp, tz=UTC)

    def create_rate_limit_response(self, rate_limit_info: dict) -> func.HttpResponse:
        """Create HTTP 429 response with rate limit headers."""
        import json

        headers = {
            "X-RateLimit-Limit": str(rate_limit_info.get("limit", 0)),
            "X-RateLimit-Remaining": str(rate_limit_info.get("remaining", 0)),
            "X-RateLimit-Reset": str(rate_limit_info.get("reset", 0)),
        }

        if "retry_after" in rate_limit_info:
            headers["Retry-After"] = str(rate_limit_info["retry_after"])

        retry_after = rate_limit_info.get("retry_after", 60)

        return func.HttpResponse(
            json.dumps(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please try again in {retry_after} seconds.",
                    "limit": rate_limit_info.get("limit"),
                    "remaining": rate_limit_info.get("remaining"),
                    "reset": rate_limit_info.get("reset"),
                }
            ),
            status_code=429,
            mimetype="application/json",
            headers=headers,
        )

    def add_rate_limit_headers(
        self, response: func.HttpResponse, rate_limit_info: dict | None
    ) -> func.HttpResponse:
        """Add rate limit headers to successful response."""
        if rate_limit_info and hasattr(response, "headers"):
            response.headers["X-RateLimit-Limit"] = str(rate_limit_info.get("limit", 0))
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_info.get("remaining", 0))
            response.headers["X-RateLimit-Reset"] = str(rate_limit_info.get("reset", 0))

        return response

    async def check_rate_limit_by_key(
        self, key: str, user_id: str | None = None, endpoint: str | None = None
    ) -> tuple[bool, dict | None]:
        """
        Check if request is within rate limits using a string key.
        Args:
            key: Rate limit key (IP address or identifier)
            user_id: Authenticated user ID (if available)
            endpoint: Endpoint path for specific limits
        Returns:
            Tuple of (is_allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_time
        """
        try:
            await self.database_service.initialize()

            # Determine rate limit config
            limit_config = self._get_limit_config_for_endpoint(user_id, endpoint)

            # Determine the actual key to use
            if user_id and (not endpoint or not endpoint.startswith("/auth")):
                final_key = f"user:{user_id}"
            elif endpoint and "auth" in endpoint:
                final_key = f"ip:{key}:auth"
            else:
                final_key = f"ip:{key}"

            # Get current window start time
            now = datetime.now(UTC)
            window_start = self._get_window_start(now, limit_config.window_seconds)
            window_id = window_start.strftime("%Y%m%d%H%M%S")

            # Document ID combines key and window
            doc_id = f"{final_key}_{window_id}"

            # Try to get or create rate limit document
            container = self.database_service.get_container_client("ratelimits")
            if not container:
                self.logger.warning("Rate limits container not initialized, allowing request")
                return True, None

            try:
                # Try to read existing document
                doc = container.read_item(item=doc_id, partition_key=final_key)
                current_count = doc.get("count", 0)

                # Check if limit exceeded
                if current_count >= limit_config.requests_per_window:
                    self.logger.warning(
                        "Rate limit exceeded",
                        key=final_key,
                        count=current_count,
                        limit=limit_config.requests_per_window,
                    )

                    reset_time = window_start.timestamp() + limit_config.window_seconds

                    return False, {
                        "limit": limit_config.requests_per_window,
                        "remaining": 0,
                        "reset": int(reset_time),
                        "retry_after": int(reset_time - now.timestamp()),
                    }

                # Increment counter
                doc["count"] = current_count + 1
                doc["lastRequest"] = now.isoformat()
                container.replace_item(item=doc_id, body=doc)

                remaining = limit_config.requests_per_window - doc["count"]
                reset_time = window_start.timestamp() + limit_config.window_seconds

                return True, {
                    "limit": limit_config.requests_per_window,
                    "remaining": remaining,
                    "reset": int(reset_time),
                }

            except Exception:
                # Document doesn't exist, create it
                doc = {
                    "id": doc_id,
                    "key": final_key,
                    "count": 1,
                    "windowStart": window_start.isoformat(),
                    "limit": limit_config.requests_per_window,
                    "ttl": limit_config.ttl,
                    "firstRequest": now.isoformat(),
                    "lastRequest": now.isoformat(),
                }

                container.create_item(body=doc)

                reset_time = window_start.timestamp() + limit_config.window_seconds

                return True, {
                    "limit": limit_config.requests_per_window,
                    "remaining": limit_config.requests_per_window - 1,
                    "reset": int(reset_time),
                }

        except Exception as e:
            self.logger.error("Rate limit check failed", error=str(e), key=key)
            # Fail open - allow request if rate limiting fails
            return True, None

    def _get_limit_config_for_endpoint(
        self, user_id: str | None, endpoint: str | None
    ) -> RateLimitConfig:
        """Determine rate limit configuration based on user and endpoint."""
        # Special limits for auth endpoints
        if endpoint and "auth" in endpoint:
            return DEFAULT_LIMITS["auth_endpoint"]

        # Authenticated users get higher limits
        if user_id:
            return DEFAULT_LIMITS["authenticated"]

        # Anonymous requests
        return DEFAULT_LIMITS["anonymous"]
