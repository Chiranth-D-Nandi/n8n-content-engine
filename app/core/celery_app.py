import os
import time
from celery import Celery
from app.core.config import settings
from app.core.logging import logger

# Initialize Celery app
celery_app = Celery(
    "matiks_content_engine",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Check if Redis is reachable, otherwise enable eager mode for smooth local running
_is_eager = settings.CELERY_ALWAYS_EAGER
if not _is_eager:
    try:
        import redis
        r = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1)
        r.ping()
    except Exception:
        logger.warning(
            f"Redis broker at {settings.CELERY_BROKER_URL} unreachable. "
            "Enabling CELERY_TASK_ALWAYS_EAGER=True for standalone local execution."
        )
        _is_eager = True

celery_app.conf.update(
    task_always_eager=_is_eager,
    task_eager_propagates=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIMEOUT,
    worker_prefetch_multiplier=1,
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "2")),
)

# Instrument Celery with OpenTelemetry
try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    CeleryInstrumentor().instrument()
except Exception:
    pass


@celery_app.task(
    bind=True,
    name="tasks.generate_reel_pipeline",
    max_retries=2,
    default_retry_delay=10
)
def generate_reel_pipeline_task(self, job_id: str, payload: dict, trace_context: dict = None):
    """
    Asynchronous Celery Task for Reel Generation.
    Executes the pipeline with stage tracking, metrics, and error handling.
    """
    from observability.tracing import extract_trace_context, get_tracer
    from app.services.pipeline_service import PipelineService
    
    tracer = get_tracer()
    parent_ctx = extract_trace_context(trace_context or {})
    
    with tracer.start_as_current_span("celery.generate_reel_pipeline", context=parent_ctx) as span:
        span.set_attribute("job_id", job_id)
        span.set_attribute("channel_id", payload.get("channel_id", "unknown"))
        
        service = PipelineService()
        return service.execute_job(job_id=job_id, payload=payload, task_instance=self)
