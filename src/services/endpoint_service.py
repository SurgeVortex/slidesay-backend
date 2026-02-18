"""
Endpoint business logic service.

Framework-agnostic business logic for all endpoints.
Can be used with Azure Functions, FastAPI, Flask, etc.
"""

import json
from dataclasses import dataclass
from typing import Any

from src.interfaces.auth_interface import IAuthService
from src.interfaces.database_interface import IDatabaseService
from src.interfaces.endpoint_interface import (
    HttpRequest,
    HttpResponse,
    IEndpointService,
)
from src.interfaces.monitoring_interface import IMonitoringService
from src.interfaces.rate_limiter_interface import IRateLimiter
from src.utils.config import Config


@dataclass
class AuthenticatedContext:
    """
    Context for an authenticated request.

    Contains user identity and request metadata extracted from the request.
    All authenticated endpoints should use this to get consistent user data.
    """

    user_id: str
    email: str | None
    token_payload: dict[str, Any]
    ip_address: str
    user_agent: str


class EndpointService(IEndpointService):
    """
    Framework-agnostic endpoint business logic.
    This service contains all business logic separated from HTTP framework.
    Azure Functions handlers become thin adapters that call these methods.
    """

    def __init__(
        self,
        auth_service: IAuthService,
        database_service: IDatabaseService,
        rate_limiter: IRateLimiter,
        config: Config,
    ):
        self.auth_service = auth_service
        self.database_service = database_service
        self.rate_limiter = rate_limiter
        self.config = config

    # =========================================================================
    # Authentication & Authorization Helpers (DRY - use these in all endpoints)
    # =========================================================================

    async def _authenticate_request(
        self, request: HttpRequest, monitor: IMonitoringService, endpoint: str
    ) -> tuple[AuthenticatedContext | None, HttpResponse | None]:
        """
        Authenticate a request and extract user context.

        This is the single source of truth for authentication. All authenticated
        endpoints should call this first.

        Args:
            request: The incoming HTTP request
            monitor: Monitoring service for logging
            endpoint: Endpoint path for logging

        Returns:
            Tuple of (AuthenticatedContext, None) on success, or
            (None, HttpResponse) with error response on failure.

        Usage:
            auth_context, error_response = await self._authenticate_request(request, monitor, "/api/items")
            if error_response:
                return error_response  # Return 401 error
            # Use auth_context.user_id, auth_context.email, etc.
        """
        # Extract Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            monitor.log_warning(
                "auth_failed", reason="Missing Authorization header", endpoint=endpoint
            )
            monitor.record_auth_event("auth", success=False)
            return None, HttpResponse(
                body=json.dumps(
                    {
                        "error": {
                            "code": "AUTHENTICATION_REQUIRED",
                            "message": "Missing Authorization header",
                        }
                    }
                ),
                status_code=401,
                headers={"Content-Type": "application/json"},
            )

        # Validate token
        token_payload = await self.auth_service.validate_token(auth_header)
        if not token_payload:
            monitor.log_warning("auth_failed", reason="Invalid token", endpoint=endpoint)
            monitor.record_auth_event("auth", success=False)
            return None, HttpResponse(
                body=json.dumps(
                    {"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired token"}}
                ),
                status_code=401,
                headers={"Content-Type": "application/json"},
            )

        # Extract user ID from 'sub' claim (standard OIDC claim for Microsoft Entra External ID)
        # Note: We use 'sub' exclusively, NOT 'oid'. The 'oid' claim is for Azure AD internal users.
        user_id = token_payload.get("sub")
        if not user_id:
            monitor.log_error("auth_failed", reason="Token missing sub claim", endpoint=endpoint)
            monitor.record_auth_event("auth", success=False)
            return None, HttpResponse(
                body=json.dumps(
                    {"error": {"code": "INVALID_TOKEN", "message": "Token missing required claims"}}
                ),
                status_code=401,
                headers={"Content-Type": "application/json"},
            )

        # Extract request metadata
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "unknown")

        return (
            AuthenticatedContext(
                user_id=user_id,
                email=token_payload.get("email") or token_payload.get("preferred_username"),
                token_payload=token_payload,
                ip_address=ip_address,
                user_agent=user_agent,
            ),
            None,
        )

    def _get_client_ip(self, request: HttpRequest) -> str:
        """
        Extract client IP address from request headers.

        Handles X-Forwarded-For (may contain multiple IPs) and X-Real-IP.
        """
        ip_address = request.headers.get(
            "X-Forwarded-For", request.headers.get("X-Real-IP", "unknown")
        )
        # X-Forwarded-For can contain multiple IPs; take the first (client)
        if "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()
        return ip_address

    async def _check_rate_limit_for_request(
        self,
        request: HttpRequest,
        auth_context: AuthenticatedContext | None,
        endpoint: str,
        monitor: IMonitoringService,
    ) -> tuple[bool, dict[str, Any] | None, HttpResponse | None]:
        """
        Check rate limit for a request.

        Args:
            request: The incoming HTTP request
            auth_context: Authenticated context if available (for user-based limits)
            endpoint: Endpoint path for rate limit key
            monitor: Monitoring service for logging

        Returns:
            Tuple of (is_allowed, rate_limit_info, error_response).
            If not allowed, error_response contains the 429 response.
        """
        # Use user ID if authenticated, otherwise use client IP
        if auth_context:
            key = auth_context.user_id
            user_id = auth_context.user_id
        else:
            key = self._get_client_ip(request)
            user_id = None

        is_allowed, rate_limit_info = await self._check_rate_limit(key, user_id, endpoint)

        if not is_allowed and rate_limit_info:
            monitor.log_warning("rate_limit_exceeded", endpoint=endpoint, user_id=user_id)
            return False, rate_limit_info, self._rate_limit_response(rate_limit_info)

        return True, rate_limit_info, None

    # =========================================================================
    # Endpoint Implementations
    # =========================================================================

    async def health_check(self, monitor: IMonitoringService) -> HttpResponse:
        """
        Health check endpoint logic.
        Returns:
            HttpResponse with health status
        """
        monitor.start_request()

        try:
            # Check database connectivity
            db_healthy = await self.database_service.health_check()

            health_status = {
                "status": "healthy" if db_healthy else "degraded",
                "version": self.config.get("APP_VERSION", "1.0.0"),
                "database": "connected" if db_healthy else "disconnected",
            }

            status_code = 200 if db_healthy else 503

            # Record metrics
            monitor.log_info("health_check", status=health_status["status"])
            monitor.record_request("/health", "GET", status_code)

            return HttpResponse(
                body=json.dumps(health_status),
                status_code=status_code,
                headers={"Content-Type": "application/json"},
            )

        except Exception as e:
            monitor.log_error("health_check_failed", error=str(e))

            return HttpResponse(
                body=json.dumps({"status": "unhealthy", "error": "Internal error"}),
                status_code=503,
                headers={"Content-Type": "application/json"},
            )

    async def login(self, request: HttpRequest, monitor: IMonitoringService) -> HttpResponse:
        """
        Login endpoint logic.
        Args:
            request: Framework-agnostic HTTP request
            monitor: Monitoring service for logging
        Returns:
            HttpResponse with user profile or error
        """
        monitor.start_request()

        try:
            # Check rate limit (stricter for auth endpoints)
            rate_limit_key = request.headers.get(
                "X-Forwarded-For", request.headers.get("X-Real-IP", "unknown")
            )
            is_allowed, rate_limit_info = await self._check_rate_limit(
                rate_limit_key, None, "/auth/login"
            )

            if not is_allowed and rate_limit_info:
                monitor.log_warning("rate_limit_exceeded", endpoint="/auth/login")
                monitor.record_request("/auth/login", "POST", 429)
                return self._rate_limit_response(rate_limit_info)

            # Validate authentication token
            auth_header = request.headers.get("Authorization", "")
            if not auth_header:
                monitor.log_warning("auth_failed", reason="Missing Authorization header")
                monitor.record_auth_event("login", success=False)
                monitor.record_request("/auth/login", "POST", 401)

                return HttpResponse(
                    body=json.dumps(
                        {
                            "error": {
                                "code": "AUTHENTICATION_REQUIRED",
                                "message": "Missing Authorization header",
                            }
                        }
                    ),
                    status_code=401,
                    headers={"Content-Type": "application/json"},
                )

            token_payload = await self.auth_service.validate_token(auth_header)

            if not token_payload:
                monitor.log_warning("auth_failed", reason="Invalid token format")
                monitor.record_auth_event("login", success=False)
                monitor.record_request("/auth/login", "POST", 401)

                return HttpResponse(
                    body=json.dumps(
                        {
                            "error": {
                                "code": "INVALID_TOKEN",
                                "message": "Invalid Authorization header format",
                            }
                        }
                    ),
                    status_code=401,
                    headers={"Content-Type": "application/json"},
                )

            # Extract request context for audit logging
            ip_address = request.headers.get(
                "X-Forwarded-For", request.headers.get("X-Real-IP", "unknown")
            )
            user_agent = request.headers.get("User-Agent", "unknown")

            # Get or create user in database
            result = await self.auth_service.get_or_create_user(
                token_payload, ip_address=ip_address, user_agent=user_agent
            )

            if not result:
                monitor.log_error("user_creation_failed", claims=token_payload)
                monitor.record_auth_event("login", success=False)
                monitor.record_request("/auth/login", "POST", 500)

                return HttpResponse(
                    body=json.dumps(
                        {
                            "error": {
                                "code": "USER_CREATION_FAILED",
                                "message": "Failed to create user profile",
                            }
                        }
                    ),
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                )

            user, is_new_user = result

            # Create audit log for login
            await monitor.create_audit_log(
                user_id=user.id,
                action="login",
                resource="/auth/login",
                method="POST",
                status_code=200,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"is_new_user": is_new_user},
            )

            # Success - log and return user profile with isNewUser flag
            monitor.log_info(
                "user_authenticated", user_id=user.id, email=user.email, is_new_user=is_new_user
            )
            monitor.record_auth_event("login", success=True, user_id=user.id)
            monitor.record_request("/auth/login", "POST", 200)

            response_body = json.dumps(
                {
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "display_name": user.display_name,
                        "roles": user.roles,
                        "created_at": user.created_at.isoformat(),
                        "last_login_at": user.last_login.isoformat(),
                    },
                    "isNewUser": is_new_user,
                }
            )

            # Add rate limit headers
            headers = {"Content-Type": "application/json"}
            if rate_limit_info:
                headers.update(self._get_rate_limit_headers(rate_limit_info))

            return HttpResponse(body=response_body, status_code=200, headers=headers)

        except Exception as e:
            monitor.log_error("login_error", error=str(e))
            monitor.record_request("/auth/login", "POST", 500)

            return HttpResponse(
                body=json.dumps(
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
                ),
                status_code=500,
                headers={"Content-Type": "application/json"},
            )

    async def get_profile(self, request: HttpRequest, monitor: IMonitoringService) -> HttpResponse:
        """
        Get user profile endpoint logic.

        Args:
            request: Framework-agnostic HTTP request
            monitor: Monitoring service for logging

        Returns:
            HttpResponse with user profile or error
        """
        monitor.start_request()
        endpoint = "/user/profile"

        try:
            # 1. Authenticate request (using centralized helper)
            auth_context, auth_error = await self._authenticate_request(request, monitor, endpoint)
            if auth_error:
                monitor.record_request(endpoint, "GET", 401)
                return auth_error

            # 2. Check rate limit (using centralized helper)
            is_allowed, rate_limit_info, rate_error = await self._check_rate_limit_for_request(
                request, auth_context, endpoint, monitor
            )
            if rate_error:
                monitor.record_request(endpoint, "GET", 429)
                return rate_error

            # Type narrowing: auth_context is guaranteed non-None (error returned above if None)
            if auth_context is None:  # pragma: no cover - defensive check
                return HttpResponse(
                    body=json.dumps(
                        {
                            "error": {
                                "code": "INTERNAL_ERROR",
                                "message": "Authentication context missing",
                            }
                        }
                    ),
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                )

            # 3. Get user from database
            result = await self.auth_service.get_or_create_user(
                auth_context.token_payload,
                ip_address=auth_context.ip_address,
                user_agent=auth_context.user_agent,
            )

            if not result:
                monitor.log_error("failed_to_get_user", user_id=auth_context.user_id)
                monitor.record_request(endpoint, "GET", 500)
                return HttpResponse(
                    body=json.dumps(
                        {
                            "error": {
                                "code": "USER_RETRIEVAL_FAILED",
                                "message": "Failed to retrieve user profile",
                            }
                        }
                    ),
                    status_code=500,
                    headers={"Content-Type": "application/json"},
                )

            user, _ = result  # Ignore is_new_user for profile endpoint

            # 4. Audit log the access
            await monitor.create_audit_log(
                user_id=user.id,
                action="get_profile",
                resource=endpoint,
                method="GET",
                status_code=200,
                ip_address=auth_context.ip_address,
                user_agent=auth_context.user_agent,
            )

            # 5. Success response
            monitor.log_info("profile_retrieved", user_id=user.id)
            monitor.record_request(endpoint, "GET", 200)

            response_body = json.dumps(
                {
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "display_name": user.display_name,
                        "roles": user.roles,
                    }
                }
            )

            # Add rate limit headers
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if rate_limit_info:
                headers.update(self._get_rate_limit_headers(rate_limit_info))

            return HttpResponse(body=response_body, status_code=200, headers=headers)

        except Exception as e:
            monitor.log_error("profile_error", error=str(e))
            monitor.record_request(endpoint, "GET", 500)

            return HttpResponse(
                body=json.dumps(
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
                ),
                status_code=500,
                headers={"Content-Type": "application/json"},
            )

    async def _check_rate_limit(
        self, key: str, user_id: str | None, endpoint: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Helper to check rate limits.
        Args:
            key: Rate limit key (IP address or identifier)
            user_id: User ID if authenticated
            endpoint: Endpoint path for specific limits
        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        try:
            is_allowed, rate_limit_info = await self.rate_limiter.check_rate_limit_by_key(
                key=key, user_id=user_id, endpoint=endpoint
            )
            return is_allowed, rate_limit_info
        except Exception:
            # Fail open - allow request if rate limiting fails
            return True, None

    def _rate_limit_response(self, rate_limit_info: dict[str, Any]) -> HttpResponse:
        """Create rate limit exceeded response."""
        headers = self._get_rate_limit_headers(rate_limit_info)
        headers["Content-Type"] = "application/json"

        if "retry_after" in rate_limit_info:
            headers["Retry-After"] = str(rate_limit_info["retry_after"])

        retry_after = rate_limit_info.get("retry_after", 60)

        return HttpResponse(
            body=json.dumps(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Please try again in {retry_after} seconds.",
                    "limit": rate_limit_info.get("limit"),
                    "remaining": rate_limit_info.get("remaining"),
                    "reset": rate_limit_info.get("reset"),
                }
            ),
            status_code=429,
            headers=headers,
        )

    def _get_rate_limit_headers(self, rate_limit_info: dict[str, Any]) -> dict[str, str]:
        """Get rate limit headers."""
        return {
            "X-RateLimit-Limit": str(rate_limit_info.get("limit", 0)),
            "X-RateLimit-Remaining": str(rate_limit_info.get("remaining", 0)),
            "X-RateLimit-Reset": str(rate_limit_info.get("reset", 0)),
        }
