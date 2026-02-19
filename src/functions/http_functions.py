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


# ------------------------------ Presentation Endpoints ------------------------------
import json

from src.services.presentation_service import PresentationService


def _get_presentation_service():
    # Use CosmosService from DI container
    return PresentationService(_get_container().get_database_service())

@app.function_name(name="CreatePresentation")
@app.route(route="presentations", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def create_presentation(req: func.HttpRequest) -> func.HttpResponse:
    """Create a presentation. Auth required."""
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    auth_svc = container.get_auth_service()

    # Auth
    generic_req = GenericHttpRequest(
        method=req.method, path=req.url, headers=dict(req.headers), body=req.get_body().decode("utf-8") if req.get_body() else None
    )
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    # Body
    try:
        data = json.loads(generic_req.body or req.get_body() or b"{}")
    except Exception:
        return func.HttpResponse(json.dumps({"error":"Malformed JSON"}), status_code=400)
    title = data.get("title")
    slides = data.get("slides")
    transcript = data.get("transcript", "")
    # If slides missing, try to generate (not implemented)
    if not slides and transcript:
        from src.services.llm_service import LLMService
        import os
        llm_svc = LLMService(api_key=os.environ.get("OPENROUTER_API_KEY", ""))
        structured = await llm_svc.structure_transcript(transcript)
        title = title or structured.get("title", "Untitled Presentation")
        slides = structured.get("slides", [])
    if not title:
        return func.HttpResponse(json.dumps({"error": "Missing title"}), status_code=400)
    if not isinstance(slides, list):
        return func.HttpResponse(json.dumps({"error": "slides must be a list"}), status_code=400)
    psvc = _get_presentation_service()
    pres = await psvc.create(user_id=user_id, title=title, slides=slides, transcript=transcript)
    return func.HttpResponse(json.dumps(pres), status_code=201, headers={"Content-Type": "application/json"})

@app.function_name(name="ListPresentations")
@app.route(route="presentations", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def list_presentations(req: func.HttpRequest) -> func.HttpResponse:
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers))
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    psvc = _get_presentation_service()
    presentations = await psvc.list_for_user(user_id=user_id)
    return func.HttpResponse(json.dumps({"presentations": presentations}), status_code=200, headers={"Content-Type": "application/json"})

@app.function_name(name="GetPresentation")
@app.route(route="presentations/{id}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def get_presentation(req: func.HttpRequest) -> func.HttpResponse:
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers))
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    pres_id = req.route_params.get("id")
    if not pres_id:
        return func.HttpResponse(json.dumps({"error": "Missing id in path"}), status_code=400)
    psvc = _get_presentation_service()
    pres = await psvc.get(user_id=user_id, presentation_id=pres_id)
    if not pres:
        return func.HttpResponse(json.dumps({"error": "Not found"}), status_code=404)
    return func.HttpResponse(json.dumps(pres), status_code=200, headers={"Content-Type": "application/json"})

@app.function_name(name="UpdatePresentation")
@app.route(route="presentations/{id}", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
async def update_presentation(req: func.HttpRequest) -> func.HttpResponse:
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers), body=req.get_body().decode("utf-8") if req.get_body() else None)
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    pres_id = req.route_params.get("id")
    if not pres_id:
        return func.HttpResponse(json.dumps({"error": "Missing id in path"}), status_code=400)
    try:
        data = json.loads(generic_req.body or req.get_body() or b"{}")
    except Exception:
        return func.HttpResponse(json.dumps({"error":"Malformed JSON"}), status_code=400)
    updates = {k: v for k,v in data.items() if k in ("title", "slides")}
    psvc = _get_presentation_service()
    pres = await psvc.update(user_id=user_id, presentation_id=pres_id, updates=updates)
    if not pres:
        return func.HttpResponse(json.dumps({"error": "Not found"}), status_code=404)
    return func.HttpResponse(json.dumps(pres), status_code=200, headers={"Content-Type": "application/json"})

@app.function_name(name="DeletePresentation")
@app.route(route="presentations/{id}", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
async def delete_presentation(req: func.HttpRequest) -> func.HttpResponse:
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers))
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    pres_id = req.route_params.get("id")
    if not pres_id:
        return func.HttpResponse(json.dumps({"error": "Missing id in path"}), status_code=400)
    psvc = _get_presentation_service()
    ok = await psvc.delete(user_id=user_id, presentation_id=pres_id)
    if not ok:
        return func.HttpResponse(json.dumps({"error": "Not found"}), status_code=404)
    return func.HttpResponse("", status_code=204)

@app.function_name(name="ExportPresentation")
@app.route(route="presentations/{id}/export", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def export_presentation(req: func.HttpRequest) -> func.HttpResponse:
    # Auth required
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers), body=req.get_body().decode("utf-8") if req.get_body() else None)
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/presentations")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)
    user_id = auth_context.user_id
    pres_id = req.route_params.get("id")
    try:
        data = json.loads(generic_req.body or req.get_body() or b"{}")
    except Exception:
        return func.HttpResponse(json.dumps({"error":"Malformed JSON"}), status_code=400)
    fmt = data.get("format")
    # For now, just mock export (return error or fake content)
    if fmt not in ("pptx", "pdf"):
        return func.HttpResponse(json.dumps({"error": "Unsupported format"}), status_code=400)
    # TODO: generate actual file (use psvc.get to get presentation)
    # For now, just return a fake file
    filename = f"presentation-{pres_id}.{fmt}"
    content_bytes = b"EXPORT_NOT_IMPLEMENTED"  # Replace with actual binary export
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type":
            "application/vnd.openxmlformats-officedocument.presentationml.presentation" if fmt == "pptx" else "application/pdf"
    }
    return func.HttpResponse(content_bytes, status_code=200, headers=headers)


# ------------------------------ Admin Endpoints ------------------------------

import os

from src.services.usage_service import UsageService
from src.functions.subscription_functions import create_checkout_session, create_customer_portal


def _get_usage_service():
    return UsageService(_get_container().get_database_service())


def _is_admin(user_id: str) -> bool:
    """Check if user is an admin. Admin IDs from ADMIN_USER_IDS env var (comma-separated)."""
    admin_ids = os.environ.get("ADMIN_USER_IDS", "").split(",")
    return user_id.strip() in [a.strip() for a in admin_ids if a.strip()]


@app.function_name(name="CreateStripeCheckout")
@app.route(route="stripe/checkout", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def create_stripe_checkout(req: func.HttpRequest) -> func.HttpResponse:
    return await create_checkout_session(req)

@app.function_name(name="CreateStripeCustomerPortal")
@app.route(route="stripe/customer-portal", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
async def create_stripe_customer_portal(req: func.HttpRequest) -> func.HttpResponse:
    return await create_customer_portal(req)


@app.function_name(name="AdminSetTier")
@app.route(route="admin/users/{userId}/tier", methods=["PUT"], auth_level=func.AuthLevel.ANONYMOUS)
async def admin_set_tier(req: func.HttpRequest) -> func.HttpResponse:
    """Admin endpoint to set a user's subscription tier without payment.
    Body: {"tier": "free"|"educator"|"pro"}
    Only accessible to users listed in ADMIN_USER_IDS env var.
    """
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers), body=req.get_body().decode("utf-8") if req.get_body() else None)
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/admin")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)

    if not _is_admin(auth_context.user_id):
        return func.HttpResponse(json.dumps({"error": "Forbidden"}), status_code=403, headers={"Content-Type": "application/json"})

    target_user_id = req.route_params.get("userId")
    if not target_user_id:
        return func.HttpResponse(json.dumps({"error": "Missing userId"}), status_code=400, headers={"Content-Type": "application/json"})

    try:
        data = json.loads(generic_req.body or req.get_body() or b"{}")
    except Exception:
        return func.HttpResponse(json.dumps({"error": "Malformed JSON"}), status_code=400, headers={"Content-Type": "application/json"})

    tier = data.get("tier")
    if tier not in ("free", "educator", "pro"):
        return func.HttpResponse(json.dumps({"error": "Invalid tier. Must be: free, educator, pro"}), status_code=400, headers={"Content-Type": "application/json"})

    usage_svc = _get_usage_service()
    try:
        usage = await usage_svc.set_tier(target_user_id, tier)
        return func.HttpResponse(
            json.dumps({"message": f"User {target_user_id} set to {tier}", "usage": usage}),
            status_code=200,
            headers={"Content-Type": "application/json"},
        )
    except ValueError as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=400, headers={"Content-Type": "application/json"})


@app.function_name(name="AdminGetUserTier")
@app.route(route="admin/users/{userId}/tier", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
async def admin_get_user_tier(req: func.HttpRequest) -> func.HttpResponse:
    """Admin endpoint to check a user's current tier and usage."""
    container = _get_container()
    monitor = container.create_monitoring_service()
    endpoint_service = _get_endpoint_service()
    generic_req = GenericHttpRequest(method=req.method, path=req.url, headers=dict(req.headers))
    auth_context, auth_error = await endpoint_service._authenticate_request(generic_req, monitor, "/admin")
    if auth_error:
        return func.HttpResponse(auth_error.body, status_code=auth_error.status_code, headers=auth_error.headers)

    if not _is_admin(auth_context.user_id):
        return func.HttpResponse(json.dumps({"error": "Forbidden"}), status_code=403, headers={"Content-Type": "application/json"})

    target_user_id = req.route_params.get("userId")
    if not target_user_id:
        return func.HttpResponse(json.dumps({"error": "Missing userId"}), status_code=400, headers={"Content-Type": "application/json"})

    usage_svc = _get_usage_service()
    usage = await usage_svc.get_usage(target_user_id)
    return func.HttpResponse(json.dumps(usage), status_code=200, headers={"Content-Type": "application/json"})


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
