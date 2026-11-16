import os
from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from app.core.config import settings
from app.core.logging import logger

_tracer = None
_propagator = TraceContextTextMapPropagator()


def setup_tracing(service_name: Optional[str] = None) -> trace.Tracer:
    global _tracer
    if _tracer is not None:
        return _tracer

    svc_name = service_name or settings.OTEL_SERVICE_NAME
    resource = Resource.create({
        "service.name": svc_name,
        "deployment.environment": settings.APP_ENV,
        "service.version": "1.0.0"
    })

    provider = TracerProvider(resource=resource)

    # Check if OTLP endpoint is configured
    otlp_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"OpenTelemetry configured with OTLP endpoint: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"Failed to initialize OTLP exporter ({e}). Falling back to noop.")
    else:
        # Development / test mode
        logger.info("OpenTelemetry initialized with in-memory provider.")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(svc_name)
    return _tracer


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        return setup_tracing()
    return _tracer


def inject_trace_context(carrier: dict) -> dict:
    """Inject W3C trace context into dict carrier (for Celery headers or HTTP headers)."""
    _propagator.inject(carrier)
    return carrier


def extract_trace_context(carrier: dict):
    """Extract W3C trace context from dict carrier."""
    return _propagator.extract(carrier)
