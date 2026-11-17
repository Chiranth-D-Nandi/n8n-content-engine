from flask import Blueprint, jsonify, request
from app.services.job_service import JobService

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/jobs", methods=["GET"])
def list_jobs():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    job_service = JobService()
    return jsonify(job_service.list_jobs(limit=limit, offset=offset))


@jobs_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    job_service = JobService()
    return jsonify(job_service.get_job(job_id))


@jobs_bp.route("/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    job_service = JobService()
    success = job_service.delete_job(job_id)
    return jsonify({"success": success, "job_id": job_id})


@jobs_bp.route("/status/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """
    Backward-compatible polling endpoint for n8n and external consumers.
    """
    job_service = JobService()
    job = job_service.get_job(job_id)
    
    outputs = job.get("outputs", [])
    output_path = outputs[0]["file"] if outputs else None
    
    return jsonify({
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job.get("stage"),
        "progress": job.get("progress", 0),
        "output_path": output_path,
        "error": job.get("error")
    })
