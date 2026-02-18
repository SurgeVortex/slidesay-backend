"""Test endpoint service business logic with dependency injection."""

import os

import pytest

from src.auth.auth_service import AuthService
from src.services.endpoint_service import EndpointService
from src.utils.config import Config
from tests.test_doubles import (
    FakeMonitoringService,
    InMemoryDatabaseService,
    InMemoryRateLimiter,
)


class TestHealthCheckEndpoint:
    """Test health check endpoint business logic."""

    @pytest.fixture
    def services(self):
        """Create service instances with test doubles."""
        # Set required environment variables for AuthService
        os.environ["AZURE_CLIENT_ID"] = "test-client-id"
        os.environ["AZURE_TENANT_ID"] = "test-tenant-id"

        db_service = InMemoryDatabaseService()
        monitoring = FakeMonitoringService()
        rate_limiter = InMemoryRateLimiter()
        config = Config()

        # Auth service needs database
        auth_service = AuthService(database_service=db_service)

        endpoint_service = EndpointService(
            auth_service=auth_service,
            database_service=db_service,
            rate_limiter=rate_limiter,
            config=config,
        )

        return {
            "endpoint": endpoint_service,
            "db": db_service,
            "monitoring": monitoring,
            "rate_limiter": rate_limiter,
            "auth": auth_service,
        }

    @pytest.mark.asyncio
    async def test_health_check_returns_200_when_db_healthy(self, services):
        """Test health check returns 200 when database is healthy."""
        # Initialize database to make it healthy
        await services["db"].initialize()

        response = await services["endpoint"].health_check(services["monitoring"])

        assert response.status_code == 200
        assert "healthy" in response.body

    @pytest.mark.asyncio
    async def test_health_check_records_metrics(self, services):
        """Test health check records monitoring metrics."""
        await services["db"].initialize()
        await services["endpoint"].health_check(services["monitoring"])

        # Verify monitoring was called
        assert len(services["monitoring"].logs) > 0
        assert any("health_check" in log["message"] for log in services["monitoring"].logs)


class TestMonitoringIntegration:
    """Test that endpoints properly integrate with monitoring."""

    @pytest.fixture
    def services(self):
        """Create service instances."""
        os.environ["AZURE_CLIENT_ID"] = "test-client-id"
        os.environ["AZURE_TENANT_ID"] = "test-tenant-id"

        db_service = InMemoryDatabaseService()
        monitoring = FakeMonitoringService()
        rate_limiter = InMemoryRateLimiter()
        config = Config()

        auth_service = AuthService(database_service=db_service)

        endpoint_service = EndpointService(
            auth_service=auth_service,
            database_service=db_service,
            rate_limiter=rate_limiter,
            config=config,
        )

        return {
            "endpoint": endpoint_service,
            "db": db_service,
            "monitoring": monitoring,
            "rate_limiter": rate_limiter,
        }

    @pytest.mark.asyncio
    async def test_all_endpoints_log_to_monitoring(self, services):
        """Test that all endpoint calls are logged."""
        await services["db"].initialize()

        initial_log_count = len(services["monitoring"].logs)

        await services["endpoint"].health_check(services["monitoring"])

        # Should have logged something
        assert len(services["monitoring"].logs) > initial_log_count

    @pytest.mark.asyncio
    async def test_monitoring_captures_trace_ids(self, services):
        """Test that monitoring service generates trace IDs for correlation."""
        await services["db"].initialize()

        # Start a request to generate trace ID
        services["monitoring"].start_request()

        await services["endpoint"].health_check(services["monitoring"])

        # Trace ID should be accessible from monitoring
        trace_id = services["monitoring"].get_trace_id()
        assert trace_id is not None
        assert len(trace_id) == 32  # 16 bytes = 32 hex chars


class TestRateLimiterDouble:
    """Test the rate limiter test double itself."""

    @pytest.mark.asyncio
    async def test_rate_limiter_enforces_limits(self):
        """Test that rate limiter correctly enforces configured limits."""
        limiter = InMemoryRateLimiter()
        limiter.set_limit("test-key", max_requests=2, window_seconds=60)

        # First two requests should succeed
        is_allowed1, info1 = await limiter.check_rate_limit_by_key("test-key")
        is_allowed2, info2 = await limiter.check_rate_limit_by_key("test-key")

        assert is_allowed1 is True
        assert is_allowed2 is True

        # Third should be denied
        is_allowed3, info3 = await limiter.check_rate_limit_by_key("test-key")
        assert is_allowed3 is False

    @pytest.mark.asyncio
    async def test_rate_limiter_provides_remaining_count(self):
        """Test that rate limiter returns remaining request count."""
        limiter = InMemoryRateLimiter()
        limiter.set_limit("test-key", max_requests=5, window_seconds=60)

        # First request
        is_allowed, info = await limiter.check_rate_limit_by_key("test-key")

        assert is_allowed is True
        assert info is not None
        assert info["limit"] == 5
        assert info["remaining"] == 4  # 5 - 1 = 4 remaining
