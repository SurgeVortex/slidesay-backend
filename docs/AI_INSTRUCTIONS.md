# AI Development Instructions

> **This document is for AI agents operating on this codebase.**
> Human developers should read [CONTRIBUTING.md](CONTRIBUTING.md) for onboarding.

## Quick Reference

| Task               | Command           | Documentation                                    |
| ------------------ | ----------------- | ------------------------------------------------ |
| Setup environment  | `make init`       | This file                                        |
| Run all checks     | `make checks`     | [CONTRIBUTING.md](CONTRIBUTING.md)               |
| Run unit tests     | `make test`       | [HOW_TO_TEST.md](HOW_TO_TEST.md)                 |
| Add new endpoint   | See pattern below | [HOW_TO_ADD_ENDPOINT.md](HOW_TO_ADD_ENDPOINT.md) |
| Add new service    | See pattern below | [HOW_TO_ADD_SERVICE.md](HOW_TO_ADD_SERVICE.md)   |
| Generate OpenAPI   | `make openapi`    | [openapi/README.md](../openapi/README.md)        |
| Start local server | `make dev`        | This file                                        |

## Architecture Summary

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        function_app.py (ENTRYPOINT)                     │
│                    Ultra-thin wrapper - DO NOT add logic here           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ imports app from
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     src/functions/http_functions.py                     │
│            HTTP Adapters - Convert Azure req → Generic req              │
│                      Lazy-loads container on first call                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ calls
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     src/services/endpoint_service.py                    │
│                   Framework-agnostic business logic                     │
│                   All HTTP logic lives here (testable)                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ uses
                                     ▼
┌───────────────────┬───────────────────┬─────────────────────────────────┐
│   IAuthService    │  IDatabaseService │    IMonitoringService           │
│   (auth/)         │  (database/)      │    (monitoring/)                │
└───────────────────┴───────────────────┴─────────────────────────────────┘
                                     ▲
                                     │ injected by
                                     │
┌─────────────────────────────────────────────────────────────────────────┐
│                         src/container.py                                │
│              Dependency Injection - singleton pattern                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Critical Rules

### 1. Never Import at Module Level (Except Types)

```python
# ❌ WRONG - breaks cold start
from src.database.cosmos_service import CosmosService
db = CosmosService()  # Fails: env vars not loaded yet

# ✅ CORRECT - lazy load
def _get_container() -> "ServiceContainer":
    global _container
    if _container is None:
        from src.container import get_container
        _container = get_container()
    return _container
```

### 2. Use TYPE_CHECKING for Type Imports

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.interfaces import IAuthService  # Only for type hints

def my_function() -> "IAuthService":  # Quote the return type
    from src.auth.auth_service import AuthService
    return AuthService()
```

### 3. All Business Logic in EndpointService

```python
# ❌ WRONG - logic in function handler
@app.route(route="users", methods=["POST"])
async def create_user(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()
    user = await database.create_user(data)  # Business logic in handler!
    return func.HttpResponse(json.dumps(user))

# ✅ CORRECT - handler only adapts
@app.route(route="users", methods=["POST"])
async def create_user(req: func.HttpRequest) -> func.HttpResponse:
    generic_req = GenericHttpRequest(...)
    response = await endpoint_service.create_user(generic_req, monitor)
    return func.HttpResponse(response.body, status_code=response.status_code)
```

### 4. Use Centralized Auth & Rate Limit Helpers (DRY)

```python
# ❌ WRONG - repeating auth logic in every endpoint
async def my_endpoint(self, request, monitor):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return HttpResponse(...)  # 401
    token = await self.auth_service.validate_token(auth_header)
    if not token:
        return HttpResponse(...)  # 401
    user_id = token.get("oid") or token.get("sub")  # WRONG: use sub only
    # ... repeated in every endpoint

# ✅ CORRECT - use centralized helpers
async def my_endpoint(self, request, monitor):
    # Auth helper handles all validation, extracts user_id from 'sub' claim
    auth_context, auth_error = await self._authenticate_request(request, monitor, "/api/items")
    if auth_error:
        return auth_error

    # Rate limit helper
    is_allowed, rate_info, rate_error = await self._check_rate_limit_for_request(
        request, auth_context, "/api/items", monitor
    )
    if rate_error:
        return rate_error

    # Now use auth_context.user_id, auth_context.ip_address, etc.
```

### 5. Every Database Query Filters by User ID

```python
# ❌ WRONG - data leak across tenants
async def get_items(self) -> list[dict]:
    return await self.database.query_items("items", "SELECT * FROM c")

# ✅ CORRECT - tenant isolation using auth_context.user_id
async def get_items(self, auth_context: AuthenticatedContext) -> list[dict]:
    return await self.database.query_items(
        "items",
        "SELECT * FROM c WHERE c.userId = @userId",
        parameters=[{"name": "@userId", "value": auth_context.user_id}],
        partition_key=auth_context.user_id
    )
```

### 6. Always Add Audit Logs

```python
await monitor.create_audit_log(
    user_id=auth_context.user_id,
    action="create_item",
    resource="/api/items",
    method="POST",
    status_code=201,
    ip_address=auth_context.ip_address,
    user_agent=auth_context.user_agent,
    metadata={"item_id": item.id}
)
```

## Common Tasks

### Adding a New Endpoint

See [HOW_TO_ADD_ENDPOINT.md](HOW_TO_ADD_ENDPOINT.md) for full walkthrough.

**Quick checklist:**

1. [ ] Add interface method to `IEndpointService`
2. [ ] Implement using `_authenticate_request()` and `_check_rate_limit_for_request()` helpers
3. [ ] Add HTTP adapter in `http_functions.py`
4. [ ] Add tests in `test_endpoint_service.py`
5. [ ] Run `make checks` and `make test`

### Adding a New Service

See [HOW_TO_ADD_SERVICE.md](HOW_TO_ADD_SERVICE.md) for full walkthrough.

**Quick checklist:**

1. [ ] Create interface in `src/interfaces/`
2. [ ] Create implementation in `src/<service_name>/`
3. [ ] Register in `container.py` with lazy loading
4. [ ] Export interface from `src/interfaces/__init__.py`
5. [ ] Add tests with fakes in `test_doubles.py`

### Running Locally

```bash
# First time setup
make init

# Start Azure Functions locally (requires Azure Functions Core Tools)
make dev

# Run all pre-commit checks
make checks

# Run unit tests only
make test

# Run with Cosmos DB emulator (for integration tests)
make integration
```

## Testing Requirements

1. **All new code must have tests** - aim for >80% coverage
2. **Use test doubles** - see `tests/test_doubles.py` for patterns
3. **Test business logic directly** - test `EndpointService` methods, not HTTP handlers
4. **Test error paths** - auth failures, validation errors, database errors

```python
# Good test structure
async def test_create_item_success(mock_services):
    """Test successful item creation with valid auth."""
    # Arrange
    endpoint_service = EndpointService(**mock_services)
    request = create_test_request(auth_token="valid-token", body={"name": "Test"})

    # Act
    response = await endpoint_service.create_item(request, mock_monitor)

    # Assert
    assert response.status_code == 201
    assert json.loads(response.body)["item"]["name"] == "Test"
```

## Error Response Format

Always return errors in this format:

```python
return HttpResponse(
    body=json.dumps({
        "error": {
            "code": "VALIDATION_ERROR",  # Machine-readable code
            "message": "Email is required"  # Human-readable message
        }
    }),
    status_code=400,
    headers={"Content-Type": "application/json"}
)
```

Error codes to use:

- `AUTHENTICATION_REQUIRED` - Missing Authorization header (401)
- `INVALID_TOKEN` - Malformed or expired token (401)
- `FORBIDDEN` - Valid token but no permission (403)
- `NOT_FOUND` - Resource doesn't exist (404)
- `VALIDATION_ERROR` - Bad input data (400)
- `RATE_LIMIT_EXCEEDED` - Too many requests (429)
- `INTERNAL_ERROR` - Server error (500)

## Environment Variables

The application expects these environment variables (injected by infrastructure):

| Variable                        | Description                   | Required |
| ------------------------------- | ----------------------------- | -------- |
| `COSMOSDB_ENDPOINT`             | Cosmos DB endpoint URL        | Yes      |
| `COSMOSDB_DATABASE_NAME`        | Database name                 | Yes      |
| `COSMOSDB_USERS_CONTAINER`      | Users container name          | Yes      |
| `COSMOSDB_AUDITLOGS_CONTAINER`  | Audit logs container          | Yes      |
| `COSMOSDB_RATELIMITS_CONTAINER` | Rate limits container         | Yes      |
| `AZURE_CLIENT_ID`               | Entra ID client ID (audience) | Yes      |
| `AZURE_TENANT_ID`               | Entra ID tenant ID            | Yes      |
| `OTEL_EXPORTER_OTLP_ENDPOINT`   | Grafana Cloud OTLP endpoint   | Yes      |
| `OTEL_EXPORTER_OTLP_HEADERS`    | Auth header for OTLP          | Yes      |

For local development, copy `local.settings.json.template` to `local.settings.json`.

## File Naming Conventions

- `*_interface.py` - Abstract base classes (contracts)
- `*_service.py` - Service implementations
- `test_*.py` - Test files
- `__init__.py` - Module exports

## Commit Messages

Use conventional commits:

- `feat: add item creation endpoint`
- `fix: handle null email in auth`
- `test: add rate limiter tests`
- `docs: update endpoint documentation`

## Pre-Deployment Checklist

Before any deployment:

1. [ ] `make checks` passes
2. [ ] `make test` passes
3. [ ] No secrets in code (run `detect-secrets scan`)
4. [ ] New endpoints have tests
5. [ ] New endpoints have audit logging
6. [ ] New database queries filter by user ID
