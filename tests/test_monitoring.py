"""Tests for MonitoringService - OpenTelemetry integration."""

from unittest.mock import Mock, patch

import pytest

from src.monitoring.monitor import MonitoringService
from tests.test_doubles import InMemoryDatabaseService


class TestMonitoringServiceTracing:
    """Test OpenTelemetry trace ID generation and correlation."""

    @pytest.fixture
    def monitoring(self):
        db = InMemoryDatabaseService()
        return MonitoringService(database_service=db)

    def test_get_trace_id_returns_32_character_hex(self, monitoring):
        """Test that trace IDs are 32 character hex strings."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_context = Mock()
            mock_context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
            mock_span.return_value.is_recording.return_value = True
            mock_span.return_value.get_span_context.return_value = mock_context

            trace_id = monitoring.get_trace_id()

            assert trace_id is not None
            assert len(trace_id) == 32
            assert trace_id == "1234567890abcdef1234567890abcdef"

    def test_get_trace_id_returns_none_when_no_active_span(self, monitoring):
        """Test that get_trace_id returns None when no span is active."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_span.return_value.is_recording.return_value = False

            trace_id = monitoring.get_trace_id()

            assert trace_id is None


class TestMonitoringServiceAuditLogs:
    """Test audit log creation with trace correlation."""

    @pytest.fixture
    def db(self):
        return InMemoryDatabaseService()

    @pytest.fixture
    def monitoring(self, db):
        return MonitoringService(database_service=db)

    @pytest.mark.asyncio
    async def test_create_audit_log_stores_user_action(self, monitoring, db):
        """Test that audit logs are created with all required fields."""
        result = await monitoring.create_audit_log(
            user_id="user-123",
            action="update_profile",
            resource="/api/user/profile",
            method="PUT",
            status_code=200,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            metadata={"field": "displayName"},
        )

        assert result is True
        assert len(db._audit_logs) == 1

        log = db._audit_logs[0]
        assert log["userId"] == "user-123"
        assert log["action"] == "update_profile"
        assert log["resource"] == "/api/user/profile"
        assert log["method"] == "PUT"
        assert log["statusCode"] == 200

    @pytest.mark.asyncio
    async def test_audit_log_includes_trace_id(self, monitoring, db):
        """Test that audit logs include trace ID for correlation."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_context = Mock()
            mock_context.trace_id = 0xDEADBEEFDEADBEEFDEADBEEFDEADBEEF
            mock_span.return_value.is_recording.return_value = True
            mock_span.return_value.get_span_context.return_value = mock_context

            await monitoring.create_audit_log(
                user_id="user-456",
                action="login",
                resource="/api/auth/login",
                method="POST",
                status_code=200,
            )

            log = db._audit_logs[0]
            assert log["traceId"] == "deadbeefdeadbeefdeadbeefdeadbeef"

    @pytest.mark.asyncio
    async def test_audit_log_returns_false_when_no_database(self):
        """Test audit logging fails gracefully when database not configured."""
        monitoring = MonitoringService(database_service=None)

        with patch.object(monitoring.logger, "warning"):
            result = await monitoring.create_audit_log(
                user_id="user-999",
                action="test",
                resource="/api/test",
                method="GET",
                status_code=200,
            )

            assert result is False


class TestMonitoringServiceLogging:
    """Test structured logging methods."""

    @pytest.fixture
    def monitoring(self):
        return MonitoringService()

    def test_log_warning_adds_trace_correlation(self, monitoring):
        """Test warning logs include trace ID."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_context = Mock()
            mock_context.trace_id = 0xAABBCCDDAABBCCDDAABBCCDDAABBCCDD
            mock_span.return_value.is_recording.return_value = True
            mock_span.return_value.get_span_context.return_value = mock_context

            with patch.object(monitoring.logger, "warning") as mock_log:
                monitoring.log_warning("rate_limit_exceeded", endpoint="/api/test")

                mock_log.assert_called_once()
                assert mock_log.call_args.kwargs["trace_id"] == "aabbccddaabbccddaabbccddaabbccdd"

    def test_log_error_adds_trace_correlation(self, monitoring):
        """Test error logs include trace ID."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_context = Mock()
            mock_context.trace_id = 0x1111222211112222111122221111222
            mock_span.return_value.is_recording.return_value = True
            mock_span.return_value.get_span_context.return_value = mock_context

            with patch.object(monitoring.logger, "error") as mock_log:
                monitoring.log_error("database_error", error="timeout")

                mock_log.assert_called_once()
                assert mock_log.call_args.kwargs["trace_id"] == "01111222211112222111122221111222"

    def test_log_debug_adds_trace_correlation(self, monitoring):
        """Test debug logs include trace ID."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_context = Mock()
            mock_context.trace_id = 0xFEDCBA9876543210FEDCBA9876543210
            mock_span.return_value.is_recording.return_value = True
            mock_span.return_value.get_span_context.return_value = mock_context

            with patch.object(monitoring.logger, "debug") as mock_log:
                monitoring.log_debug("cache_hit", key="user:123")

                mock_log.assert_called_once()
                assert mock_log.call_args.kwargs["trace_id"] == "fedcba9876543210fedcba9876543210"


class TestMonitoringServiceMetrics:
    """Test metrics recording."""

    @pytest.fixture
    def monitoring(self):
        return MonitoringService()

    def test_record_request_with_explicit_duration(self, monitoring):
        """Test recording request with explicit duration."""
        with patch.object(monitoring._http_request_duration, "record") as mock_record:
            monitoring.record_request("/api/users", "POST", 201, duration_ms=45.5)

            mock_record.assert_called_once()
            assert mock_record.call_args[0][0] == 45.5

    def test_record_request_calculates_duration_from_start(self, monitoring):
        """Test that duration is calculated if not provided."""
        import time

        monitoring.start_request()
        time.sleep(0.01)

        with patch.object(monitoring._http_request_duration, "record") as mock_record:
            monitoring.record_request("/api/test", "GET", 200)

            duration = mock_record.call_args[0][0]
            assert duration >= 10.0

    def test_record_database_operation(self, monitoring):
        """Test database operation metrics."""
        with patch.object(monitoring._db_operation_counter, "add") as mock_counter:
            with patch.object(monitoring._db_operation_duration, "record") as mock_duration:
                monitoring.record_database_operation("query", 15.5, success=True)

                mock_counter.assert_called_once()
                assert mock_counter.call_args[0][1]["db.operation"] == "query"
                assert mock_counter.call_args[0][1]["db.success"] is True

                mock_duration.assert_called_once()
                assert mock_duration.call_args[0][0] == 15.5

    def test_record_metric_logs_custom_metric(self, monitoring):
        """Test custom metric recording."""
        with patch.object(monitoring.logger, "info") as mock_log:
            monitoring.record_metric("checkout_total", 99.99, labels={"currency": "USD"})

            mock_log.assert_called_once()
            assert mock_log.call_args.kwargs["metric_name"] == "checkout_total"
            assert mock_log.call_args.kwargs["value"] == 99.99
            assert mock_log.call_args.kwargs["currency"] == "USD"


class TestMonitoringServiceErrorHandling:
    """Test error handling in monitoring service."""

    @pytest.fixture
    def db(self):
        return InMemoryDatabaseService()

    @pytest.fixture
    def monitoring(self, db):
        return MonitoringService(database_service=db)

    @pytest.mark.asyncio
    async def test_audit_log_handles_database_error(self, monitoring, db):
        """Test audit logging handles database failures."""
        db._should_fail = True

        with patch.object(monitoring.logger, "error") as mock_log:
            result = await monitoring.create_audit_log(
                user_id="user-error",
                action="test",
                resource="/api/test",
                method="GET",
                status_code=200,
            )

            assert result is False
            mock_log.assert_called_once()


class TestFakeMonitoringServiceBehavior:
    """Test the FakeMonitoringService test double for DI-based testing."""

    @pytest.fixture
    def fake_monitoring(self):
        """Create a FakeMonitoringService for testing."""
        from tests.test_doubles import FakeMonitoringService

        return FakeMonitoringService()

    def test_fake_monitoring_generates_trace_id(self, fake_monitoring):
        """Test that FakeMonitoringService generates trace IDs."""
        trace_id = fake_monitoring.get_trace_id()

        assert trace_id is not None
        assert len(trace_id) == 32  # 16 bytes = 32 hex chars

    def test_fake_monitoring_start_request_generates_new_trace_id(self, fake_monitoring):
        """Test that start_request generates a new trace ID."""
        fake_monitoring.get_trace_id()
        fake_monitoring.start_request()
        second_trace = fake_monitoring.get_trace_id()

        # After start_request, we should have a (potentially different) trace ID
        assert second_trace is not None
        assert len(second_trace) == 32

    def test_fake_monitoring_logs_info_messages(self, fake_monitoring):
        """Test that info logs are captured."""
        fake_monitoring.info("test message", key="value")

        assert len(fake_monitoring.logs) == 1
        assert fake_monitoring.logs[0]["level"] == "info"
        assert fake_monitoring.logs[0]["message"] == "test message"
        assert fake_monitoring.logs[0]["key"] == "value"

    def test_fake_monitoring_logs_warning_messages(self, fake_monitoring):
        """Test that warning logs are captured."""
        fake_monitoring.warning("warning message", alert=True)

        assert len(fake_monitoring.logs) == 1
        assert fake_monitoring.logs[0]["level"] == "warning"
        assert fake_monitoring.logs[0]["message"] == "warning message"
        assert fake_monitoring.logs[0]["alert"] is True

    def test_fake_monitoring_logs_error_messages(self, fake_monitoring):
        """Test that error logs are captured."""
        fake_monitoring.error("error occurred", error_code=500)

        assert len(fake_monitoring.logs) == 1
        assert fake_monitoring.logs[0]["level"] == "error"
        assert fake_monitoring.logs[0]["message"] == "error occurred"
        assert fake_monitoring.logs[0]["error_code"] == 500

    def test_fake_monitoring_logs_debug_messages(self, fake_monitoring):
        """Test that debug logs are captured."""
        fake_monitoring.debug("debug info", data={"x": 1})

        assert len(fake_monitoring.logs) == 1
        assert fake_monitoring.logs[0]["level"] == "debug"
        assert fake_monitoring.logs[0]["message"] == "debug info"

    def test_fake_monitoring_records_http_requests(self, fake_monitoring):
        """Test that HTTP request metrics are recorded."""
        fake_monitoring.record_request("/api/users", "GET", 200, duration_ms=15.5)

        assert len(fake_monitoring.metrics) == 1
        assert fake_monitoring.metrics[0]["type"] == "http_request"
        assert fake_monitoring.metrics[0]["route"] == "/api/users"
        assert fake_monitoring.metrics[0]["method"] == "GET"
        assert fake_monitoring.metrics[0]["status_code"] == 200
        assert fake_monitoring.metrics[0]["duration_ms"] == 15.5

    def test_fake_monitoring_records_errors_for_4xx_5xx(self, fake_monitoring):
        """Test that error metrics are recorded for 4xx and 5xx responses."""
        fake_monitoring.record_request("/api/error", "POST", 500, duration_ms=5.0)

        # Should have both request and error metrics
        assert len(fake_monitoring.metrics) == 2
        assert fake_monitoring.metrics[0]["type"] == "http_request"
        assert fake_monitoring.metrics[1]["type"] == "http_error"
        assert fake_monitoring.metrics[1]["status_code"] == 500

    def test_fake_monitoring_records_database_operations(self, fake_monitoring):
        """Test that database operation metrics are recorded."""
        fake_monitoring.record_database_operation("query", 10.5, success=True)

        assert len(fake_monitoring.metrics) == 1
        assert fake_monitoring.metrics[0]["type"] == "database_operation"
        assert fake_monitoring.metrics[0]["operation"] == "query"
        assert fake_monitoring.metrics[0]["duration_ms"] == 10.5
        assert fake_monitoring.metrics[0]["success"] is True

    def test_fake_monitoring_records_auth_events(self, fake_monitoring):
        """Test that auth events are recorded."""
        fake_monitoring.record_auth_event("login", success=True, user_id="user-123")

        assert len(fake_monitoring.metrics) == 1
        assert fake_monitoring.metrics[0]["type"] == "auth_event"
        assert fake_monitoring.metrics[0]["event_type"] == "login"
        assert fake_monitoring.metrics[0]["success"] is True
        assert fake_monitoring.metrics[0]["user_id"] == "user-123"

    def test_fake_monitoring_records_custom_metrics(self, fake_monitoring):
        """Test that custom metrics are recorded."""
        fake_monitoring.record_metric("orders_processed", 42.0, labels={"region": "US"})

        assert len(fake_monitoring.metrics) == 1
        assert fake_monitoring.metrics[0]["type"] == "custom_metric"
        assert fake_monitoring.metrics[0]["name"] == "orders_processed"
        assert fake_monitoring.metrics[0]["value"] == 42.0
        assert fake_monitoring.metrics[0]["labels"]["region"] == "US"

    @pytest.mark.asyncio
    async def test_fake_monitoring_creates_audit_logs(self, fake_monitoring):
        """Test that audit logs are created with trace correlation."""
        fake_monitoring.start_request()

        result = await fake_monitoring.create_audit_log(
            user_id="user-abc",
            action="update_profile",
            resource="/api/user/profile",
            method="PUT",
            status_code=200,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            metadata={"field": "name"},
        )

        assert result is True
        assert len(fake_monitoring.audit_logs) == 1

        log = fake_monitoring.audit_logs[0]
        assert log["userId"] == "user-abc"
        assert log["action"] == "update_profile"
        assert log["resource"] == "/api/user/profile"
        assert log["method"] == "PUT"
        assert log["statusCode"] == 200
        assert log["traceId"] is not None
        assert log["ipAddress"] == "192.168.1.1"
        assert log["userAgent"] == "TestAgent/1.0"
        assert log["metadata"]["field"] == "name"

    def test_fake_monitoring_log_aliases_work(self, fake_monitoring):
        """Test that log_info, log_warning, log_error are aliases."""
        fake_monitoring.log_info("info msg", labels={"a": "1"})
        fake_monitoring.log_warning("warn msg", labels={"b": "2"})
        fake_monitoring.log_error("error msg", labels={"c": "3"})

        assert len(fake_monitoring.logs) == 3
        assert fake_monitoring.logs[0]["level"] == "info"
        assert fake_monitoring.logs[1]["level"] == "warning"
        assert fake_monitoring.logs[2]["level"] == "error"
