# How to Add a New Endpoint

This guide walks through adding a new HTTP endpoint to the backend. We'll use creating a "list items" endpoint as an example.

## Step 1: Define the Interface Contract

First, add the method signature to `src/interfaces/endpoint_interface.py`:

```python
# src/interfaces/endpoint_interface.py

class IEndpointService(ABC):
    # ... existing methods ...

    @abstractmethod
    async def list_items(
        self, request: HttpRequest, monitor: "IMonitoringService"
    ) -> HttpResponse:
        """
        List items for the authenticated user.

        Args:
            request: HTTP request with Authorization header
            monitor: Monitoring service for logging/metrics

        Returns:
            HttpResponse with paginated items list or error
        """
        pass
```

## Step 2: Implement Business Logic

Add the implementation in `src/services/endpoint_service.py`. **Use the centralized helpers for DRY code:**

```python
# src/services/endpoint_service.py

async def list_items(
    self, request: HttpRequest, monitor: IMonitoringService
) -> HttpResponse:
    """List items for authenticated user with pagination."""
    monitor.start_request()
    endpoint = "/api/items"

    try:
        # 1. Authenticate (using centralized helper - handles all auth logic)
        auth_context, auth_error = await self._authenticate_request(request, monitor, endpoint)
        if auth_error:
            monitor.record_request(endpoint, "GET", 401)
            return auth_error

        # 2. Rate limiting (using centralized helper)
        is_allowed, rate_limit_info, rate_error = await self._check_rate_limit_for_request(
            request, auth_context, endpoint, monitor
        )
        if rate_error:
            monitor.record_request(endpoint, "GET", 429)
            return rate_error

        # 3. Parse and validate query parameters
        page = 1
        page_size = 20
        if request.query_params:
            try:
                page = int(request.query_params.get("page", "1"))
                page_size = min(int(request.query_params.get("pageSize", "20")), 100)
            except ValueError:
                return HttpResponse(
                    body=json.dumps({
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Invalid pagination parameters"
                        }
                    }),
                    status_code=400,
                    headers={"Content-Type": "application/json"}
                )

        # 4. Query database (ALWAYS filter by user_id for tenant isolation)
        # Use typed repository methods when available
        items = await self.database_service.query_items(
            container_name="items",
            query="SELECT * FROM c WHERE c.userId = @userId ORDER BY c.createdAt DESC",
            parameters=[{"name": "@userId", "value": auth_context.user_id}],
            partition_key=auth_context.user_id
        )

        # Apply pagination in memory (or use OFFSET/LIMIT in query for large datasets)
        start = (page - 1) * page_size
        paginated_items = items[start:start + page_size]

        # 5. Audit log the access
        await monitor.create_audit_log(
            user_id=auth_context.user_id,
            action="list_items",
            resource=endpoint,
            method="GET",
            status_code=200,
            ip_address=auth_context.ip_address,
            user_agent=auth_context.user_agent,
            metadata={"page": page, "page_size": page_size, "count": len(paginated_items)}
        )

        # 6. Success response
        monitor.log_info("list_items_success", user_id=auth_context.user_id, count=len(paginated_items))
        monitor.record_request(endpoint, "GET", 200)

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if rate_limit_info:
            headers.update(self._get_rate_limit_headers(rate_limit_info))

        return HttpResponse(
            body=json.dumps({
                "items": paginated_items,
                "pagination": {
                    "page": page,
                    "pageSize": page_size,
                    "count": len(paginated_items),
                    "totalCount": len(items)
                }
            }),
            status_code=200,
            headers=headers
        )

    except Exception as e:
        monitor.log_error("list_items_failed", error=str(e))
        monitor.record_request(endpoint, "GET", 500)

        return HttpResponse(
            body=json.dumps({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to list items"
                }
            }),
            status_code=500,
            headers={"Content-Type": "application/json"}
        )
```

### Key Points - DRY Helpers

The `EndpointService` provides centralized helpers:

| Helper                            | Purpose                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------- |
| `_authenticate_request()`         | Validates token, extracts user ID (`sub` claim), returns `AuthenticatedContext` |
| `_check_rate_limit_for_request()` | Checks rate limits, returns error response if exceeded                          |
| `_get_client_ip()`                | Extracts client IP from headers (handles X-Forwarded-For)                       |
| `_rate_limit_response()`          | Creates 429 response with proper headers                                        |

**Always use these helpers instead of writing authentication/rate-limiting code directly.**

## Step 3: Add HTTP Adapter

Add the Azure Functions route in `src/functions/http_functions.py`:

```python
# src/functions/http_functions.py

@app.function_name(name="list_items")
@app.route(route="items", methods=["GET"], auth_level=AuthLevel.ANONYMOUS)
async def list_items(req: func.HttpRequest) -> func.HttpResponse:
    """
    List items endpoint - thin Azure Functions adapter.

    Query Parameters:
        page (int): Page number (default: 1)
        pageSize (int): Items per page (default: 20, max: 100)
    """
    container = _get_container()
    endpoint_service = _get_endpoint_service()
    monitor = container.create_monitoring_service()

    # Convert Azure Functions request to generic request
    generic_req = GenericHttpRequest(
        method=req.method,
        path=req.url,
        headers=dict(req.headers),
        query_params=dict(req.params) if req.params else None
    )

    # Call business logic
    response = await endpoint_service.list_items(generic_req, monitor)

    # Add trace ID to response headers
    headers = response.headers or {}
    trace_id = monitor.get_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    # Convert to Azure Functions response
    return func.HttpResponse(
        response.body,
        status_code=response.status_code,
        headers=headers
    )
```

## Step 4: Write Tests

Add tests in `tests/test_endpoint_service.py`:

```python
# tests/test_endpoint_service.py

import pytest
import json
from src.services.endpoint_service import EndpointService
from src.interfaces import HttpRequest

class TestListItems:
    """Tests for list_items endpoint."""

    @pytest.fixture
    def endpoint_service(self, mock_auth_service, mock_database_service, mock_rate_limiter, mock_config):
        """Create endpoint service with mock dependencies."""
        return EndpointService(
            auth_service=mock_auth_service,
            database_service=mock_database_service,
            rate_limiter=mock_rate_limiter,
            config=mock_config
        )

    @pytest.mark.asyncio
    async def test_list_items_success(self, endpoint_service, mock_monitor, mock_database_service):
        """Test successful item listing."""
        # Arrange
        mock_database_service.query_items.return_value = [
            {"id": "item-1", "name": "Test Item", "userId": "user-123"}
        ]
        request = HttpRequest(
            method="GET",
            path="/api/items",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Act
        response = await endpoint_service.list_items(request, mock_monitor)

        # Assert
        assert response.status_code == 200
        body = json.loads(response.body)
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "Test Item"
        assert body["pagination"]["page"] == 1

    @pytest.mark.asyncio
    async def test_list_items_no_auth(self, endpoint_service, mock_monitor):
        """Test list items without authentication."""
        request = HttpRequest(
            method="GET",
            path="/api/items",
            headers={}  # No Authorization header
        )

        response = await endpoint_service.list_items(request, mock_monitor)

        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_list_items_rate_limited(self, endpoint_service, mock_monitor, mock_rate_limiter):
        """Test rate limiting on list items."""
        mock_rate_limiter.check_rate_limit.return_value = (False, {"retry_after": 60})
        request = HttpRequest(
            method="GET",
            path="/api/items",
            headers={"Authorization": "Bearer valid-token"}
        )

        response = await endpoint_service.list_items(request, mock_monitor)

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_list_items_filters_by_user_id(self, endpoint_service, mock_monitor, mock_database_service, mock_auth_service):
        """Test that items are filtered by authenticated user's ID."""
        # This verifies tenant isolation
        mock_auth_service.validate_token.return_value = {"oid": "user-456", "sub": "user-456"}

        request = HttpRequest(
            method="GET",
            path="/api/items",
            headers={"Authorization": "Bearer valid-token"}
        )

        await endpoint_service.list_items(request, mock_monitor)

        # Verify query includes user ID filter
        mock_database_service.query_items.assert_called_once()
        call_args = mock_database_service.query_items.call_args
        assert any(p["value"] == "user-456" for p in call_args.kwargs.get("parameters", []))
```

## Step 5: Run Checks

```bash
# Format and lint
make checks

# Run tests
make test

# If both pass, you're ready to commit!
```

## Checklist

Before considering the endpoint complete:

- [ ] Interface method added to `IEndpointService`
- [ ] Implementation uses `_authenticate_request()` helper (DRY)
- [ ] Implementation uses `_check_rate_limit_for_request()` helper (DRY)
- [ ] All database queries filter by `auth_context.user_id` (tenant isolation)
- [ ] Audit log created via `monitor.create_audit_log()`
- [ ] Success/error metrics recorded via `monitor.record_request()`
- [ ] HTTP adapter is thin (just request/response conversion)
- [ ] Tests cover success path
- [ ] Tests cover auth failure (no header, invalid token)
- [ ] Tests cover rate limiting
- [ ] Tests verify user ID filtering (tenant isolation)
- [ ] `make checks` passes
- [ ] `make test` passes

## Common Patterns

### User ID - Use `sub` Claim Only

For Microsoft Entra External ID, always use the `sub` claim:

```python
# The _authenticate_request() helper does this for you, returning:
# auth_context.user_id  # From 'sub' claim

# If you need to access it manually (you shouldn't):
user_id = token_payload.get("sub")  # NOT oid - 'sub' is the OIDC standard

# 'oid' is for Azure AD internal users (work/school accounts)
# 'sub' is the standard OIDC claim for External ID
```

### Parse Request Body

```python
try:
    body = json.loads(request.body) if request.body else {}
except json.JSONDecodeError:
    return HttpResponse(
        body=json.dumps({"error": {"code": "VALIDATION_ERROR", "message": "Invalid JSON body"}}),
        status_code=400,
        headers={"Content-Type": "application/json"}
    )
```

### Validate Required Fields

```python
required_fields = ["name", "description"]
missing = [f for f in required_fields if f not in body]
if missing:
    return HttpResponse(
        body=json.dumps({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": f"Missing required fields: {', '.join(missing)}"
            }
        }),
        status_code=400,
        headers={"Content-Type": "application/json"}
    )
```

### Get Client IP (Already Done by Helper)

The `_authenticate_request()` helper extracts IP automatically:

```python
# auth_context.ip_address already contains the client IP
# It handles X-Forwarded-For with multiple IPs

# If you need to do it manually (rare):
ip_address = self._get_client_ip(request)
```
