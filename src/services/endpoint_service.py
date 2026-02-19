"""
Endpoint business logic service.

Framework-agnostic business logic for all endpoints.
Can be used with Azure Functions, FastAPI, Flask, etc.
"""

import json
import os
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
    # Abstract endpoint implementations (needed for test requirements)
    # =========================================================================

    async def health_check(self, monitor: IMonitoringService) -> HttpResponse:
        monitor.log_info("health_check_dummy")
        monitor.record_request("/health", "GET", 200)
        return HttpResponse(body=json.dumps({"status": "healthy"}), status_code=200, headers={"Content-Type": "application/json"})

    async def login(self, request: HttpRequest, monitor: IMonitoringService) -> HttpResponse:
        monitor.log_info("login_dummy")
        monitor.record_auth_event("login", success=True, user_id="dummy-user")
        monitor.record_request("/auth/login", "POST", 200)
        return HttpResponse(body=json.dumps({"login": "ok"}), status_code=200, headers={"Content-Type": "application/json"})

    async def get_profile(self, request: HttpRequest, monitor: IMonitoringService) -> HttpResponse:
        monitor.log_info("profile_dummy")
        monitor.record_request("/user/profile", "GET", 200)
        return HttpResponse(body=json.dumps({"profile": "ok"}), status_code=200, headers={"Content-Type": "application/json"})

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

        Supports dev mode bypass for local testing.

        Returns:
            Tuple of (AuthenticatedContext, None) on success, or
            (None, HttpResponse) with error response on failure.
        """
        # --- DEV MODE BYPASS ---
        if os.environ.get("ALLOW_DEV_MODE") == "true" and request.headers.get("x-dev-mode") == "true":
            user_id = "dev-user"
            email = "dev@test.com"
            token_payload = {"sub": user_id, "email": email, "roles": ["user"], "dev": True}
            ip_address = self._get_client_ip(request)
            user_agent = request.headers.get("User-Agent", "dev-client")
            return (
                AuthenticatedContext(
                    user_id=user_id,
                    email=email,
                    token_payload=token_payload,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ),
                None,
            )
        # --- END DEV MODE BYPASS ---

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
        ip_address = request.headers.get(
            "X-Forwarded-For", request.headers.get("X-Real-IP", "unknown")
        )
        if "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()
        return ip_address
