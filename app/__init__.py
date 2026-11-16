import time
import uuid
from pathlib import Path
from flask import Flask, request, g, send_from_directory, jsonify
from flask_cors import CORS

from app.core.config import settings
from app.core.logging import logger
from app.core.exceptions import AppException
from app.api.health import health_bp
from app.api.webhook import webhook_bp
from app.api.jobs import jobs_bp
from app.api.channels import channels_bp
from app.api.styles import styles_bp
from app.api.genres import genres_bp
from app.api.metrics import metrics_bp
from observability.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_FLIGHT,
)
from observability.tracing import setup_tracing


def create_app(config_override: dict = None) -> Flask:
    """
    Application Factory Pattern for Matiks Content Engine.
    """
    app = Flask(
        __name__,
        static_folder=str(Path("dashboard").resolve()),
        static_url_path="/dashboard/static"
    )
    
    # Configure OpenTelemetry Tracing
    setup_tracing()
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        FlaskInstrumentor().instrument_app(app)
    except Exception:
        pass

    # CORS configuration
    origins = settings.CORS_ORIGINS
    if "*" in origins:
        CORS(app, resources={r"/*": {"origins": "*"}})
    else:
        CORS(app, resources={r"/*": {"origins": origins}})

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(channels_bp)
    app.register_blueprint(styles_bp)
    app.register_blueprint(genres_bp)
    app.register_blueprint(metrics_bp)

    # ── REQUEST LIFECYCLE & TELEMETRY ────────────────────────────
    @app.before_request
    def before_request():
        g.request_start_time = time.time()
        # Request correlation ID
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        HTTP_REQUESTS_IN_FLIGHT.inc()

    @app.after_request
    def after_request(response):
        HTTP_REQUESTS_IN_FLIGHT.dec()
        
        # Inject correlation ID header
        if hasattr(g, "request_id"):
            response.headers["X-Request-ID"] = g.request_id
            
        # Record metrics
        if hasattr(g, "request_start_time"):
            duration = time.time() - g.request_start_time
            endpoint = request.endpoint or request.path
            status_code = str(response.status_code)
            
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method, endpoint=endpoint
            ).observe(duration)
            
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method, endpoint=endpoint, status=status_code
            ).inc()
            
        return response

    # ── CENTRALIZED EXCEPTION HANDLERS ───────────────────────────
    @app.errorhandler(AppException)
    def handle_app_exception(err: AppException):
        logger.warning(f"Handled application exception: {err.error_code} - {err.message}")
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(404)
    def handle_404(err):
        return jsonify({"error": "Resource not found", "error_code": "NOT_FOUND"}), 404

    @app.errorhandler(500)
    def handle_500(err):
        logger.error("Unhandled internal server error", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "error_code": "INTERNAL_SERVER_ERROR"
        }), 500

    # ── STATIC ASSETS & DASHBOARD ────────────────────────────────
    @app.route("/")
    @app.route("/dashboard")
    def dashboard():
        return send_from_directory("dashboard", "index.html")

    @app.route("/outputs/<channel_id>/<filename>")
    def serve_output_file(channel_id: str, filename: str):
        outputs_dir = Path("outputs") / channel_id
        return send_from_directory(str(outputs_dir.resolve()), filename)

    return app
