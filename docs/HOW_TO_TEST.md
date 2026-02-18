# How to Test

This guide covers testing patterns and best practices for this codebase.

## Quick Commands

```bash
# Run all unit tests
make test

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_endpoint_service.py

# Run specific test
pytest tests/test_endpoint_service.py::TestLogin::test_login_success

# Run integration tests (requires Cosmos emulator)
make integration
```

## Test Architecture

```text
tests/
├── conftest.py              # Shared fixtures (create fakes here)
├── test_doubles.py          # Fake implementations (in-memory services)
├── test_auth.py             # Auth service tests
├── test_database.py         # Database service tests
├── test_endpoint_service.py # Endpoint business logic tests
├── test_monitoring.py       # Monitoring service tests
└── test_<feature>.py        # Feature-specific tests
```

## Testing Philosophy

### 1. Test Business Logic, Not Framework

We test `EndpointService` methods directly, not Azure Functions handlers:

```python
# ✅ GOOD - Test the business logic
async def test_login_success():
    endpoint_service = EndpointService(...)
    response = await endpoint_service.login(request, monitor)
    assert response.status_code == 200

# ❌ AVOID - Testing Azure Functions handler directly
async def test_login_handler():
    # Requires Azure Functions runtime
    pass
```

### 2. What Are Test Doubles? (And How They Work with DI)

**Test doubles ARE what you inject via dependency injection.** They're the same concept.

In production, the DI container injects real services:

```python
container = ServiceContainer()
endpoint_service = EndpointService(
    auth_service=container.get_auth_service(),      # Real AuthService
    database_service=container.get_database_service(),  # Real CosmosService
    ...
)
```

In tests, YOU inject fake/mock services:

```python
endpoint_service = EndpointService(
    auth_service=FakeAuthService(),       # Fake (test double)
    database_service=FakeDatabaseService(),  # Fake (test double)
    ...
)
```

**Types of test doubles:**

| Type     | Purpose                           | Example                   |
| -------- | --------------------------------- | ------------------------- |
| **Fake** | Simplified working implementation | In-memory database        |
| **Mock** | Records calls, verifies behavior  | `Mock(spec=IAuthService)` |
| **Stub** | Returns fixed values              | Always returns `True`     |

**We prefer Fakes** because they have real logic and catch more bugs.

### 3. Every Endpoint Needs These Tests

For every endpoint, write tests covering:

| Test Case               | What to Assert                             |
| ----------------------- | ------------------------------------------ |
| **Success**             | Status 200, correct response body          |
| **No auth header**      | Status 401, code `AUTHENTICATION_REQUIRED` |
| **Invalid token**       | Status 401, code `INVALID_TOKEN`           |
| **Rate limit exceeded** | Status 429, `Retry-After` header           |
| **Tenant isolation**    | User A cannot see User B's data            |
| **Validation error**    | Status 400, code `VALIDATION_ERROR`        |
| **Database error**      | Status 500, generic error message          |

## Comprehensive Test Example

Here's a **complete test suite** for an endpoint, showing all required tests:

```python
# tests/test_endpoint_service.py

import pytest
import json
from src.services.endpoint_service import EndpointService
from src.interfaces import HttpRequest


class TestGetProfile:
    """
    Comprehensive tests for get_profile endpoint.

    Tests cover: success, auth failures, rate limiting, tenant isolation.
    """

    @pytest.fixture
    def fake_auth(self):
        """Auth service with configurable token validation."""
        from tests.test_doubles import FakeAuthService
        fake = FakeAuthService()
        # Configure a valid token by default
        fake.add_valid_token("valid-token", {
            "sub": "user-123",  # Note: 'sub' not 'oid' for External ID
            "email": "test@example.com",
            "name": "Test User"
        })
        return fake

    @pytest.fixture
    def fake_db(self):
        """Database service with in-memory storage."""
        from tests.test_doubles import FakeDatabaseService
        return FakeDatabaseService()

    @pytest.fixture
    def fake_rate_limiter(self):
        """Rate limiter - allows all by default."""
        from tests.test_doubles import FakeRateLimiter
        limiter = FakeRateLimiter()
        limiter.set_allowed(True)
        return limiter

    @pytest.fixture
    def fake_monitor(self):
        """Monitoring service that records calls."""
        from tests.test_doubles import FakeMonitoringService
        return FakeMonitoringService()

    @pytest.fixture
    def endpoint_service(self, fake_auth, fake_db, fake_rate_limiter):
        """Create endpoint service with all fake dependencies."""
        from src.utils.config import Config
        return EndpointService(
            auth_service=fake_auth,
            database_service=fake_db,
            rate_limiter=fake_rate_limiter,
            config=Config()
        )

    # =========================================================================
    # SUCCESS TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_profile_success(self, endpoint_service, fake_auth, fake_db, fake_monitor):
        """Test successful profile retrieval."""
        # Arrange: Add user to fake database
        fake_db.add_user({
            "id": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "display_name": "Test",
            "roles": ["user"]
        })

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer valid-token"}
        )

        # Act
        response = await endpoint_service.get_profile(request, fake_monitor)

        # Assert
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["user"]["id"] == "user-123"
        assert body["user"]["email"] == "test@example.com"

    # =========================================================================
    # AUTHENTICATION TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_profile_no_auth_header(self, endpoint_service, fake_monitor):
        """Test 401 when Authorization header is missing."""
        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={}  # No Authorization header
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_get_profile_invalid_token(self, endpoint_service, fake_auth, fake_monitor):
        """Test 401 when token is invalid."""
        # Token "bad-token" is not in fake_auth's valid tokens
        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer bad-token"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["error"]["code"] == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_get_profile_expired_token(self, endpoint_service, fake_auth, fake_monitor):
        """Test 401 when token is expired."""
        # Configure fake to reject this token
        fake_auth.add_expired_token("expired-token")

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer expired-token"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 401

    # =========================================================================
    # RATE LIMITING TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_profile_rate_limited(self, endpoint_service, fake_rate_limiter, fake_monitor):
        """Test 429 when rate limit is exceeded."""
        # Configure rate limiter to reject
        fake_rate_limiter.set_allowed(False, retry_after=60)

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer valid-token"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"

    @pytest.mark.asyncio
    async def test_rate_limit_headers_on_success(self, endpoint_service, fake_rate_limiter, fake_db, fake_monitor):
        """Test that rate limit headers are included on successful requests."""
        fake_db.add_user({"id": "user-123", "email": "test@example.com"})
        fake_rate_limiter.set_allowed(True, limit=100, remaining=99, reset=3600)

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer valid-token"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "99"

    # =========================================================================
    # TENANT ISOLATION TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_user_can_only_see_own_profile(self, endpoint_service, fake_auth, fake_db, fake_monitor):
        """Test that User A cannot access User B's profile."""
        # Setup two users
        fake_db.add_user({"id": "user-A", "email": "a@example.com"})
        fake_db.add_user({"id": "user-B", "email": "b@example.com"})

        # User A's token
        fake_auth.add_valid_token("token-A", {"sub": "user-A", "email": "a@example.com"})

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer token-A"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        # User A should only see their own profile
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["user"]["id"] == "user-A"
        assert body["user"]["email"] == "a@example.com"
        # Should NOT see user-B's data
        assert "b@example.com" not in response.body

    # =========================================================================
    # ERROR HANDLING TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_database_error_returns_500(self, endpoint_service, fake_db, fake_monitor):
        """Test graceful handling of database errors."""
        # Configure database to throw error
        fake_db.set_error(Exception("Connection timeout"))

        request = HttpRequest(
            method="GET",
            path="/user/profile",
            headers={"Authorization": "Bearer valid-token"}
        )

        response = await endpoint_service.get_profile(request, fake_monitor)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body["error"]["code"] == "INTERNAL_ERROR"
        # Should NOT expose internal error details
        assert "Connection timeout" not in response.body
```

### Configuring Fakes

```python
# Auth Service
fake_auth = FakeAuthService()
fake_auth.add_valid_token("valid-token", {"sub": "user-123", "email": "test@example.com"})
fake_auth.add_expired_token("expired-token")

# Database Service
fake_db = FakeDatabaseService()
fake_db.add_user({"id": "user-123", "email": "test@example.com"})
fake_db.add_items("user-123", [{"id": "item-1", "name": "Test"}])
fake_db.set_error(Exception("Simulate failure"))  # Make queries fail

# Rate Limiter
fake_limiter = FakeRateLimiter()
fake_limiter.set_allowed(True, limit=100, remaining=99)  # Allow with headers
fake_limiter.set_allowed(False, retry_after=60)  # Block requests
```

## More Test Patterns

### Testing Lists with Pagination

```python
@pytest.mark.asyncio
async def test_list_items_pagination(endpoint_service, fake_db, fake_monitor, fake_auth):
    """Test that pagination works correctly."""
    # Add many items
    items = [{"id": f"item-{i}", "name": f"Item {i}"} for i in range(25)]
    fake_db.add_items("user-123", items)

    # Request first page
    request = create_test_request(
        method="GET",
        path="/api/items",
        query_params={"page": "1", "pageSize": "10"}
    )

    response = await endpoint_service.list_items(request, fake_monitor)
    body = json.loads(response.body)

    assert response.status_code == 200
    assert len(body["items"]) == 10
    assert body["pagination"]["total"] == 25
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pageSize"] == 10
    assert body["pagination"]["hasMore"] == True


@pytest.mark.asyncio
async def test_list_items_empty(endpoint_service, fake_db, fake_monitor):
    """Test empty list returns proper structure."""
    # No items added - empty database

    request = create_test_request(method="GET", path="/api/items")

    response = await endpoint_service.list_items(request, fake_monitor)
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["items"] == []
    assert body["pagination"]["total"] == 0
```

### Testing Tenant Isolation

```python
@pytest.mark.asyncio
async def test_user_cannot_access_other_users_data(endpoint_service, fake_db, fake_auth, fake_monitor):
    """Test that users can only see their own data."""
    # Setup: Both users have items in database
    fake_db.add_items("user-A", [{"id": "item-1", "name": "A's item"}])
    fake_db.add_items("user-B", [{"id": "item-2", "name": "B's item"}])

    # User B's token
    fake_auth.add_valid_token("token-B", {"sub": "user-B", "email": "b@example.com"})

    # Request as user-B
    request = create_test_request(auth_token="token-B")

    response = await endpoint_service.list_items(request, fake_monitor)

    # Should only return user-B's items
    assert response.status_code == 200
    body = json.loads(response.body)
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "B's item"
    # Should NOT contain A's data
    assert "A's item" not in json.dumps(body)
```

### Testing Rate Limiting (Success AND Failure)

Always test both paths: requests within limits AND requests that exceed limits.

```python
@pytest.mark.asyncio
async def test_rate_limiting_allows_normal_requests(endpoint_service, fake_limiter, fake_db, fake_monitor):
    """Test that normal requests within limits succeed with headers."""
    fake_db.add_items("user-123", [{"id": "item-1"}])
    fake_limiter.set_allowed(True, limit=100, remaining=99, reset=3600)

    request = create_test_request()

    response = await endpoint_service.list_items(request, fake_monitor)

    # Request succeeds
    assert response.status_code == 200
    # Rate limit headers present
    assert response.headers["X-RateLimit-Limit"] == "100"
    assert response.headers["X-RateLimit-Remaining"] == "99"


@pytest.mark.asyncio
async def test_rate_limiting_blocks_excessive_requests(endpoint_service, fake_limiter, fake_monitor):
    """Test that rate limited requests return 429."""
    fake_limiter.set_allowed(False, retry_after=60)

    request = create_test_request()

    response = await endpoint_service.list_items(request, fake_monitor)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    body = json.loads(response.body)
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
```

### Testing Validation

```python
@pytest.mark.asyncio
async def test_create_item_validates_required_fields(endpoint_service, mock_monitor):
    """Test that required fields are validated."""
    request = HttpRequest(
        method="POST",
        path="/api/items",
        headers={"Authorization": "Bearer valid-token"},
        body=json.dumps({"description": "No name field"})  # Missing 'name'
    )

    response = await endpoint_service.create_item(request, mock_monitor)

    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in body["error"]["message"].lower()
```

### Testing Database Errors

```python
@pytest.mark.asyncio
async def test_handles_database_error_gracefully(endpoint_service, mock_db, mock_monitor):
    """Test that database errors return 500 with generic message."""
    mock_db.query_items.side_effect = Exception("Connection timeout")

    request = create_authenticated_request()

    response = await endpoint_service.list_items(request, mock_monitor)

    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["error"]["code"] == "INTERNAL_ERROR"
    # Should NOT expose internal error details
    assert "Connection timeout" not in body["error"]["message"]
```

## Fixtures

### Shared Fixtures in `conftest.py`

```python
# tests/conftest.py
import pytest
from tests.test_doubles import (
    FakeAuthService,
    FakeDatabaseService,
    FakeRateLimiter,
    FakeMonitoringService,
)

@pytest.fixture
def fake_auth():
    """Fake auth service with valid default token."""
    service = FakeAuthService()
    # Note: Use 'sub' claim for Microsoft Entra External ID
    service.add_valid_token("valid-token", {
        "sub": "test-user-123",
        "email": "test@example.com"
    })
    return service

@pytest.fixture
def fake_db():
    """Fake database service."""
    return FakeDatabaseService()

@pytest.fixture
def fake_limiter():
    """Fake rate limiter that allows all requests."""
    limiter = FakeRateLimiter()
    limiter.set_allowed(True, limit=100, remaining=99)
    return limiter

@pytest.fixture
def fake_monitor():
    """Fake monitoring service."""
    return FakeMonitoringService()

@pytest.fixture
def endpoint_service(fake_auth, fake_db, fake_limiter):
    """Endpoint service with all fake dependencies injected."""
    from src.services.endpoint_service import EndpointService
    from src.utils.config import Config

    # This is DI in action: injecting fakes (test doubles) into the service
    return EndpointService(
        auth_service=fake_auth,
        database_service=fake_db,
        rate_limiter=fake_limiter,
        config=Config()
    )
```

### Helper Functions

```python
# tests/conftest.py

def create_test_request(
    method: str = "GET",
    path: str = "/api/test",
    headers: dict | None = None,
    body: str | None = None,
    query_params: dict | None = None,
    auth_token: str = "valid-token"
) -> HttpRequest:
    """Create a test request with sensible defaults."""
    default_headers = {"Authorization": f"Bearer {auth_token}"}
    if headers:
        default_headers.update(headers)

    return HttpRequest(
        method=method,
        path=path,
        headers=default_headers,
        body=body,
        query_params=query_params
    )
```

## Integration Tests

For tests that need a real database:

```bash
# Start Cosmos DB emulator
make start-emulator

# Run integration tests
make integration
```

### Marking Integration Tests

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_real_user():
    """Test with real Cosmos DB emulator."""
    # This test requires the emulator running
    pass
```

Run only unit tests (skip integration):

```bash
pytest tests/ -m "not integration"
```

## Coverage

### Check Coverage

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

### Generate HTML Report

```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Coverage Targets

- Overall: >80%
- Critical paths (auth, database): >90%
- Error handling: >80%

## Debugging Tests

### Run with Verbose Output

```bash
pytest tests/ -v
```

### Run with Print Statements

```bash
pytest tests/ -s
```

### Run with Debugger

```python
def test_something():
    import pdb; pdb.set_trace()
    # Execution pauses here
```

### See Full Assertions

```bash
pytest tests/ --tb=long
```
