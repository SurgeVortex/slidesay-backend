"""
Azure Functions Backend Template - Main Application

Thin adapter layer that converts Azure Functions requests to framework-agnostic
business logic. All business logic lives in EndpointService.

This makes it easy to:
- Swap to FastAPI, Flask, etc by creating a different adapter
- Test business logic without Azure Functions runtime
- Keep framework-specific code minimal

Production-ready template for Micro SaaS with:
- Microsoft Entra External ID authentication
- Azure Cosmos DB with Managed Identity
- OpenTelemetry observability → Grafana Cloud
- Audit logging
"""

from typing import TYPE_CHECKING

import azure.functions as func
from azure.functions import AuthLevel

from src.interfaces import HttpRequest as GenericHttpRequest
from src.monitoring.otel_config import initialize_opentelemetry

if TYPE_CHECKING:
    from src.container import ServiceContainer
    from src.interfaces import IEndpointService

# Initialize OpenTelemetry SDK at module load (safe - no env vars required)
initialize_opentelemetry()

# Create function app FIRST, before any container initialization
# This ensures Azure Functions can discover the app and its routes
app = func.FunctionApp(http_auth_level=AuthLevel.ANONYMOUS)

# Lazy-loaded container and service (initialized on first request)
# This avoids import-time failures when env vars aren't yet available
_container: "ServiceContainer | None" = None
_endpoint_service: "IEndpointService | None" = None


def _get_container() -> "ServiceContainer":
    """Lazy-load the service container on first use."""
    global _container
    if _container is None:
        from src.container import get_container

        _container = get_container()
    return _container


def _get_endpoint_service() -> "IEndpointService":
    """Lazy-load the endpoint service on first use."""
    global _endpoint_service
    if _endpoint_service is None:
        _endpoint_service = _get_container().get_endpoint_service()
    if _endpoint_service is None:  # pragma: no cover - defensive check
        raise RuntimeError("Failed to initialize endpoint service")
    return _endpoint_service


@app.function_name(name="health")
@app.route(route="health", methods=["GET"], auth_level=AuthLevel.ANONYMOUS)
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint - thin Azure Functions adapter."""
    container = _get_container()
    endpoint_service = _get_endpoint_service()
    monitor = container.create_monitoring_service()

    # Call business logic
    response = await endpoint_service.health_check(monitor)

    # Add trace ID to response headers for debugging
    headers = response.headers or {}
    trace_id = monitor.get_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    # Convert to Azure Functions response
    return func.HttpResponse(response.body, status_code=response.status_code, headers=headers)


@app.function_name(name="auth_login")
@app.route(route="auth/login", methods=["POST"], auth_level=AuthLevel.ANONYMOUS)
async def auth_login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Login endpoint - thin Azure Functions adapter.
    Frontend Flow:
    1. User authenticates with Microsoft Entra External ID (OAuth2)
    2. Frontend receives access token
    3. Frontend calls this endpoint with: Authorization: Bearer <token>
    4. Backend validates token, creates/updates user in database
    5. Returns user profile with isNewUser flag
    Rate Limited: 10 requests per minute per IP
    """
    container = _get_container()
    endpoint_service = _get_endpoint_service()
    monitor = container.create_monitoring_service()

    # Convert Azure Functions request to generic request
    generic_req = GenericHttpRequest(
        method=req.method,
        path=req.url,
        headers=dict(req.headers),
        body=req.get_body().decode("utf-8") if req.get_body() else None,
    )

    # Call business logic
    response = await endpoint_service.login(generic_req, monitor)

    # Add trace ID to response headers
    headers = response.headers or {}
    trace_id = monitor.get_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    # Convert to Azure Functions response
    return func.HttpResponse(response.body, status_code=response.status_code, headers=headers)


@app.function_name(name="user_profile")
@app.route(route="user/profile", methods=["GET"], auth_level=AuthLevel.ANONYMOUS)
async def get_user_profile(req: func.HttpRequest) -> func.HttpResponse:
    """
    User profile endpoint - thin Azure Functions adapter.
    Rate Limited: 100 requests per minute for authenticated users
    """
    container = _get_container()
    endpoint_service = _get_endpoint_service()
    monitor = container.create_monitoring_service()

    # Convert Azure Functions request to generic request
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers))

    # Call business logic
    response = await endpoint_service.get_profile(generic_req, monitor)

    # Add trace ID to response headers
    headers = response.headers or {}
    trace_id = monitor.get_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    # Convert to Azure Functions response
    return func.HttpResponse(response.body, status_code=response.status_code, headers=headers)
