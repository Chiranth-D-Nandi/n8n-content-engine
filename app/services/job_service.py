import uuid
from typing import Dict, Any, List, Optional
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreateRequest, JobResponse
from app.core.celery_app import generate_reel_pipeline_task
from app.core.exceptions import NotFoundException
from observability.tracing import inject_trace_context
from observability.metrics import JOBS_SUBMITTED_TOTAL, JOBS_QUEUED_GAUGE


class JobService:
    def __init__(self, repo: JobRepository = None):
        self.repo = repo or JobRepository()

    def submit_job(self, req: JobCreateRequest) -> Dict[str, Any]:
        """
        Creates job in DB, increments metrics, and dispatches Celery task.
        Returns immediately with job_id and poll_url.
        """
        job_id = str(uuid.uuid4())[:12]
        payload = req.dict()
        
        job = self.repo.create_job(
            job_id=job_id,
            channel_id=req.channel_id,
            payload=payload
        )
        
        JOBS_SUBMITTED_TOTAL.labels(channel_id=req.channel_id).inc()
        JOBS_QUEUED_GAUGE.inc()
        
        # Inject OpenTelemetry trace context across Celery task boundary
        trace_carrier = {}
        inject_trace_context(trace_carrier)
        
        # Dispatch Celery async task
        generate_reel_pipeline_task.delay(
            job_id=job_id,
            payload=payload,
            trace_context=trace_carrier
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Pipeline queued for execution",
            "poll_url": f"/jobs/{job_id}"
        }

    def get_job(self, job_id: str) -> Dict[str, Any]:
        job = self.repo.get_job(job_id)
        if not job:
            raise NotFoundException(f"Job '{job_id}' not found.")
        return job

    def list_jobs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        return self.repo.list_jobs(limit=limit, offset=offset)

    def get_stats(self) -> Dict[str, int]:
        return self.repo.get_stats()
