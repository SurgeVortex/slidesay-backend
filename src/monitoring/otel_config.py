"""
OpenTelemetry Configuration

Configures OpenTelemetry SDK to send traces, metrics, and logs to Grafana Cloud
via OTLP (OpenTelemetry Protocol) with batching for optimal performance.
"""

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)
_initialized = False


def get_resource() -> Resource:
    """
    Create OpenTelemetry resource with service metadata.
    Resources identify your service in Grafana Cloud.
    """
    config = Config()

    return Resource.create(
        {
            SERVICE_NAME: config.get("OTEL_SERVICE_NAME") or "backend-template",
            SERVICE_VERSION: config.get("APP_VERSION") or "1.0.0",
            "environment": config.get("ENVIRONMENT") or "development",
            "deployment.environment": config.get("ENVIRONMENT") or "development",
        }
    )


def configure_tracing() -> TracerProvider | None:
    """
    Configure distributed tracing with batched export to Grafana Cloud.
    Traces show request flow through your application.
    Batching reduces overhead by sending spans in groups.
    """
    config = Config()

    # Get OTLP endpoint for traces
    otlp_endpoint = config.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not configured, tracing disabled")
        return None

    # Get authorization headers (Grafana Cloud ingestion token)
    otlp_headers = config.get("OTEL_EXPORTER_OTLP_HEADERS")
    headers = {}
    if otlp_headers:
        # Parse "key=value,key2=value2" format
        for pair in otlp_headers.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()

    try:
        # Create tracer provider with resource
        resource = get_resource()
        provider = TracerProvider(resource=resource)

        # Create OTLP span exporter
        span_exporter = OTLPSpanExporter(
            endpoint=f"{otlp_endpoint}/v1/traces",
            headers=headers,
        )

        # Add batch processor (exports every 5s or 512 spans)
        span_processor = BatchSpanProcessor(
            span_exporter,
            max_queue_size=2048,
            schedule_delay_millis=5000,  # Export every 5 seconds
            max_export_batch_size=512,
            export_timeout_millis=30000,
        )
        provider.add_span_processor(span_processor)

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        logger.info("OpenTelemetry tracing configured", endpoint=otlp_endpoint)
        return provider

    except Exception as e:
        logger.error("Failed to configure OpenTelemetry tracing", error=str(e))
        return None


def configure_metrics() -> MeterProvider | None:
    """
    Configure metrics with batched export to Grafana Cloud.
    Metrics track counters, gauges, and histograms.
    Periodic export sends metrics every 60 seconds.
    """
    config = Config()

    # Get OTLP endpoint for metrics
    otlp_endpoint = config.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not configured, metrics disabled")
        return None

    # Get authorization headers
    otlp_headers = config.get("OTEL_EXPORTER_OTLP_HEADERS")
    headers = {}
    if otlp_headers:
        for pair in otlp_headers.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()

    try:
        # Create metric exporter
        metric_exporter = OTLPMetricExporter(
            endpoint=f"{otlp_endpoint}/v1/metrics",
            headers=headers,
        )

        # Create periodic reader (exports every 60s)
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=60000,  # Export every 60 seconds
            export_timeout_millis=30000,
        )

        # Create meter provider with resource
        resource = get_resource()
        provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )

        # Set as global meter provider
        metrics.set_meter_provider(provider)

        logger.info("OpenTelemetry metrics configured", endpoint=otlp_endpoint)
        return provider

    except Exception as e:
        logger.error("Failed to configure OpenTelemetry metrics", error=str(e))
        return None


def configure_instrumentation() -> None:
    """
    Configure auto-instrumentation for HTTP clients.
    Auto-instrumentation creates spans automatically for:
    - HTTPX HTTP client requests
    """
    try:
        # Instrument HTTPX (used by Cosmos DB SDK and other HTTP clients)
        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX auto-instrumentation enabled")

    except Exception as e:
        logger.error("Failed to configure auto-instrumentation", error=str(e))


def initialize_opentelemetry() -> None:
    """
    Initialize OpenTelemetry SDK with tracing, metrics, and instrumentation.
    Call this once at application startup (in function_app.py or container.py).
    """
    global _initialized

    if _initialized:
        logger.debug("OpenTelemetry already initialized")
        return

    try:
        logger.info("Initializing OpenTelemetry SDK")

        # Configure tracing (return value intentionally unused)
        configure_tracing()

        # Configure metrics (return value intentionally unused)
        configure_metrics()

        # Configure auto-instrumentation
        configure_instrumentation()

        _initialized = True
        logger.info("OpenTelemetry SDK initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize OpenTelemetry SDK", error=str(e))
        # Don't raise - allow app to continue without telemetry


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for creating custom spans."""
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for creating custom metrics."""
    return metrics.get_meter(name)


def get_current_trace_id() -> str | None:
    """
    Get the current trace ID for correlating logs and responses.
    Returns:
        Trace ID as hex string or None if no active span
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        trace_id = span.get_span_context().trace_id
        return format(trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """
    Get the current span ID for correlating logs.
    Returns:
        Span ID as hex string or None if no active span
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        span_id = span.get_span_context().span_id
        return format(span_id, "016x")
    return None
