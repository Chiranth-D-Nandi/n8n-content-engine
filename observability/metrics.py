from prometheus_client import Counter, Histogram, Gauge

# ── API METRICS ──────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Histogram of HTTP request latencies in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being handled"
)

# ── JOB METRICS ──────────────────────────────────────────────
JOBS_SUBMITTED_TOTAL = Counter(
    "jobs_submitted_total",
    "Total number of generation jobs submitted",
    ["channel_id"]
)

JOBS_COMPLETED_TOTAL = Counter(
    "jobs_completed_total",
    "Total number of generation jobs successfully completed",
    ["channel_id", "backend"]
)

JOBS_FAILED_TOTAL = Counter(
    "jobs_failed_total",
    "Total number of generation jobs failed",
    ["channel_id", "error_type"]
)

JOBS_QUEUED_GAUGE = Gauge(
    "jobs_queued",
    "Current number of queued jobs waiting for execution"
)

JOBS_RUNNING_GAUGE = Gauge(
    "jobs_running",
    "Current number of jobs actively running in worker"
)

JOB_DURATION_SECONDS = Histogram(
    "job_duration_seconds",
    "Total end-to-end execution time for completed jobs",
    ["channel_id", "backend"],
    buckets=[10, 30, 60, 120, 300, 600, 900, 1200, 1800]
)

STAGE_DURATION_SECONDS = Histogram(
    "stage_duration_seconds",
    "Duration of individual pipeline stages in seconds",
    ["stage"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600]
)

JOB_RETRIES_TOTAL = Counter(
    "job_retries_total",
    "Total number of retry attempts triggered for pipeline tasks",
    ["stage"]
)

# ── ML METRICS ───────────────────────────────────────────────
ML_INFERENCE_REQUESTS = Counter(
    "ml_inference_requests_total",
    "Total number of ML inference requests",
    ["model", "backend"]
)

ML_INFERENCE_LATENCY = Histogram(
    "ml_inference_latency_seconds",
    "Latency of ML inference calls",
    ["model", "backend"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 180.0, 600.0]
)

ML_MODEL_LOAD_DURATION_SECONDS = Gauge(
    "ml_model_load_duration_seconds",
    "Duration taken to load ML model weights into memory",
    ["model"]
)

ML_BACKEND_AVAILABILITY = Gauge(
    "ml_backend_availability",
    "Availability status of ML backends (1 = Available, 0 = Unavailable)",
    ["backend"]
)

ML_BACKEND_ERRORS = Counter(
    "ml_backend_errors_total",
    "Count of inference backend errors or exceptions",
    ["model", "backend", "error_type"]
)

GPU_QUOTA_REMAINING = Gauge(
    "gpu_quota_remaining_percent",
    "Remaining quota for GPU endpoints if reported by provider",
    ["provider"]
)
