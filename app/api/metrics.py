from flask import Blueprint, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.route("/metrics", methods=["GET"])
def metrics():
    """
    Exposes application and ML metrics in standard Prometheus format.
    """
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
