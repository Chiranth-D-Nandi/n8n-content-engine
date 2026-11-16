from flask import Blueprint, request, jsonify
from pydantic import ValidationError
from app.services.job_service import JobService
from app.schemas.job import JobCreateRequest
from app.core.exceptions import ValidationException
from app.core.security import check_rate_limit

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/webhook/matiks-reel", methods=["POST"])
def webhook_generate():
    """
    Primary generation endpoint.
    Triggered by n8n workflow or browser dashboard.
    """
    check_rate_limit()
    
    payload = request.get_json(silent=True) or {}
    
    try:
        req = JobCreateRequest(**payload)
    except ValidationError as e:
        field = e.errors()[0]['loc'][-1] if e.errors()[0].get('loc') else "unknown"
        raise ValidationException(
            message=f"Missing or invalid field: {field}",
            details={"errors": e.errors()}
        )

    job_service = JobService()
    result = job_service.submit_job(req)
    
    return jsonify(result), 202
