"""Test configuration and fixtures for OpenTelemetry and Microsoft Entra ID."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["AZURE_CLIENT_ID"] = "test-client-id"
os.environ["AZURE_TENANT_ID"] = "test-tenant-id"
os.environ["COSMOS_ENDPOINT"] = "https://test.documents.azure.com:443/"
os.environ["COSMOS_DATABASE_NAME"] = "test_db"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
os.environ["OTEL_SERVICE_NAME"] = "test-service"


@pytest.fixture
def mock_database_service():
    """Mock database service with ChainedTokenCredential."""
    mock = Mock()
    mock.health_check = AsyncMock(return_value=True)
    mock.get_user_by_id = AsyncMock(return_value=None)
    mock.create_user = AsyncMock(return_value=True)
    mock.update_user = AsyncMock(return_value=True)
    mock.create_audit_log = AsyncMock(return_value=True)
    mock.get_audit_logs = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_monitoring_service():
    """Mock monitoring service using OpenTelemetry."""
    mock = Mock()
    mock.start_request = Mock(return_value=None)
    mock.info = Mock(return_value=None)
    mock.warning = Mock(return_value=None)
    mock.error = Mock(return_value=None)
    mock.debug = Mock(return_value=None)
    mock.record_request_metric = Mock(return_value=None)
    mock.record_auth_metric = Mock(return_value=None)
    mock.record_database_metric = Mock(return_value=None)
    mock.create_audit_log = AsyncMock(return_value=None)
    mock.get_trace_id = Mock(return_value="1234567890abcdef1234567890abcdef")
    return mock


@pytest.fixture
def mock_auth_service():
    """Mock authentication service for Microsoft Entra ID JWT validation."""
    from src.auth.auth_service import User

    mock = AsyncMock()

    # Mock validate_token to return valid JWT payload
    mock.validate_token.return_value = {
        "sub": "test-user-123",
        "email": "test@example.com",
        "name": "Test User",
        "aud": "test-client-id",
        "iss": "https://login.microsoftonline.com/test-tenant-id/v2.0",
        "exp": datetime.now(UTC).timestamp() + 3600,
        "iat": datetime.now(UTC).timestamp(),
    }

    # Mock get_or_create_user to return (User, bool) tuple
    test_user = User(
        id="test-user-123",
        email="test@example.com",
        name="Test User",
        display_name="Test User",
        roles=["user"],
        created_at=datetime.now(UTC),
        last_login=datetime.now(UTC),
        is_active=True,
    )
    mock.get_or_create_user.return_value = (test_user, False)

    return mock


@pytest.fixture
def valid_jwt_token():
    """Generate a valid JWT token payload for testing."""
    return {
        "sub": "test-user-123",
        "oid": "test-user-123",
        "email": "test@example.com",
        "name": "Test User",
        "given_name": "Test",
        "family_name": "User",
        "aud": "test-client-id",
        "iss": "https://login.microsoftonline.com/test-tenant-id/v2.0",
        "exp": datetime.now(UTC).timestamp() + 3600,
        "nbf": datetime.now(UTC).timestamp() - 60,
        "iat": datetime.now(UTC).timestamp(),
    }


@pytest.fixture
def sample_http_request():
    """Create a sample HTTP request for testing."""
    from unittest.mock import Mock

    request = Mock()
    request.method = "GET"
    request.url = "http://localhost:7071/api/test"
    request.headers = {
        # Use clearly non-secret test placeholders to avoid secrets detection
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
        "X-Trace-Id": "trace-test-0001",
    }
    request.params = {}
    request.get_json.return_value = {"test": "data"}
    return request


@pytest.fixture
def sample_user_data():
    """Sample user data for testing (no passwords)."""
    return {
        "id": "test-user-123",
        "userId": "test-user-123",
        "email": "test@example.com",
        "name": "Test User",
        "displayName": "Test User",
        "roles": ["user"],
        "createdAt": datetime.now(UTC).isoformat(),
        "lastLoginAt": datetime.now(UTC).isoformat(),
        "isActive": True,
    }


@pytest.fixture
def sample_audit_log():
    """Sample audit log data for testing."""
    return {
        "id": "audit-123",
        "userId": "test-user-123",
        "action": "user_login",
        "timestamp": datetime.now(UTC).isoformat(),
        "ipAddress": "192.168.1.1",
        "userAgent": "Mozilla/5.0",
        "traceId": "trace-test-0001",
        "details": {"method": "JWT", "provider": "EntraID"},
    }
