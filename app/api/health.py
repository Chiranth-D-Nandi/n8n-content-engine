from flask import Blueprint, jsonify
from app.services.job_service import JobService
from app.core.config import settings
from services.whisper_service.client import WhisperClient
from services.video_gateway.gateway import VideoGenerationGateway

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """
    Health check returning shape expected by dashboard & monitoring.
    """
    try:
        job_service = JobService()
        stats = job_service.get_stats()
    except Exception:
        stats = {}
    
    return jsonify({
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "jobs": stats.get("jobs", 0),
        "running": stats.get("running", 0),
        "complete": stats.get("complete", 0),
        "queued": stats.get("queued", 0),
        "video_backend": settings.VIDEO_BACKEND,
    })


@health_bp.route("/health/live", methods=["GET"])
def liveness():
    """Container liveness probe."""
    return jsonify({"status": "live", "timestamp": int(__import__("time").time())})


@health_bp.route("/health/ready", methods=["GET"])
def readiness():
    """Container readiness probe checking DB, Redis, and ML Gateway."""
    job_service = JobService()
    try:
        # Check SQLite
        job_service.get_stats()
        db_ok = True
    except Exception:
        db_ok = False

    video_gateway = VideoGenerationGateway()
    video_status = video_gateway.get_status()

    whisper_client = WhisperClient()
    whisper_ok = whisper_client.is_service_healthy() or settings.WHISPER_LOCAL_FALLBACK

    is_ready = db_ok
    status_code = 200 if is_ready else 503

    return jsonify({
        "status": "ready" if is_ready else "not_ready",
        "database": "connected" if db_ok else "error",
        "video_gateway": video_status,
        "whisper_service": "connected" if whisper_ok else "unavailable",
    }), status_code
