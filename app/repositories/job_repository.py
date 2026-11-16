import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.repositories.base import BaseRepository
from app.schemas.job import JobStatus, PipelineStage, JobResponse, ReelOutput, StageDetail


class JobRepository(BaseRepository):
    def create_job(self, job_id: str, channel_id: str, payload: dict) -> Dict[str, Any]:
        created_at = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, channel_id, status, stage, progress, payload,
                    outputs, failed_reels, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    channel_id,
                    JobStatus.QUEUED.value,
                    PipelineStage.INIT.value,
                    0,
                    json.dumps(payload),
                    json.dumps([]),
                    json.dumps([]),
                    created_at,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            job = dict(row)
            job["payload"] = json.loads(job["payload"]) if job["payload"] else {}
            job["outputs"] = json.loads(job["outputs"]) if job["outputs"] else []
            job["failed_reels"] = json.loads(job["failed_reels"]) if job["failed_reels"] else []
            
            # Fetch stages
            stage_cursor = conn.execute(
                "SELECT * FROM job_stages WHERE job_id = ? ORDER BY id ASC", (job_id,)
            )
            job["stages"] = [dict(s) for s in stage_cursor.fetchall()]
            
            # Add poll url
            job["poll_url"] = f"/jobs/{job_id}"
            return job

    def list_jobs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cursor.fetchall()
            jobs = []
            for row in rows:
                j = dict(row)
                j["payload"] = json.loads(j["payload"]) if j["payload"] else {}
                j["outputs"] = json.loads(j["outputs"]) if j["outputs"] else []
                j["failed_reels"] = json.loads(j["failed_reels"]) if j["failed_reels"] else []
                j["poll_url"] = f"/jobs/{j['job_id']}"
                jobs.append(j)
            return jobs

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        stage: Optional[PipelineStage] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        backend_used: Optional[str] = None,
    ):
        with self.transaction() as conn:
            updates = ["status = ?"]
            params = [status.value]
            
            if stage is not None:
                updates.append("stage = ?")
                params.append(stage.value)
            if progress is not None:
                updates.append("progress = ?")
                params.append(progress)
            if error is not None:
                updates.append("error = ?")
                params.append(error)
            if error_type is not None:
                updates.append("error_type = ?")
                params.append(error_type)
            if backend_used is not None:
                updates.append("backend_used = ?")
                params.append(backend_used)
                
            if status == JobStatus.RUNNING:
                updates.append("started_at = COALESCE(started_at, ?)")
                params.append(datetime.utcnow().isoformat())
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                completed_at = datetime.utcnow().isoformat()
                updates.append("completed_at = ?")
                params.append(completed_at)
                
            params.append(job_id)
            query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?"
            conn.execute(query, tuple(params))

    def record_stage(
        self,
        job_id: str,
        stage_name: str,
        status: str,
        duration_seconds: float = 0.0,
        error: Optional[str] = None,
    ):
        now = datetime.utcnow().isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO job_stages (
                    job_id, stage_name, status, duration_seconds, error,
                    started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, stage_name, status, duration_seconds, error, now, now),
            )

    def record_artifact(
        self,
        job_id: str,
        artifact_type: str,
        file_path: str,
        file_size_mb: float = 0.0,
        mime_type: str = "video/mp4",
        metadata: Optional[dict] = None,
    ):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO job_artifacts (
                    job_id, artifact_type, file_path, file_size_mb, mime_type, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    artifact_type,
                    file_path,
                    file_size_mb,
                    mime_type,
                    json.dumps(metadata or {}),
                ),
            )

    def complete_job(
        self,
        job_id: str,
        outputs: List[Dict[str, Any]],
        failed_reels: List[Dict[str, Any]],
        duration_seconds: float,
        backend_used: str = "MOCK",
    ):
        status = JobStatus.COMPLETED if outputs else JobStatus.FAILED
        stage = PipelineStage.COMPLETED if outputs else PipelineStage.FAILED
        now = datetime.utcnow().isoformat()
        
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, stage = ?, progress = 100, outputs = ?, failed_reels = ?,
                    completed_at = ?, duration_seconds = ?, backend_used = ?
                WHERE job_id = ?
                """,
                (
                    status.value,
                    stage.value,
                    json.dumps(outputs),
                    json.dumps(failed_reels),
                    now,
                    duration_seconds,
                    backend_used,
                    job_id,
                ),
            )
            
            # Also record artifacts in table
            for o in outputs:
                conn.execute(
                    """
                    INSERT INTO job_artifacts (job_id, artifact_type, file_path, file_size_mb, mime_type)
                    VALUES (?, 'final_reel', ?, ?, 'video/mp4')
                    """,
                    (job_id, o.get("file", ""), o.get("size_mb", 0.0)),
                )

    def get_stats(self) -> Dict[str, int]:
        with self.transaction() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                    SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as complete,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) as queued
                FROM jobs
            """)
            row = cursor.fetchone()
            return {
                "jobs": row["total"] or 0,
                "running": row["running"] or 0,
                "complete": row["complete"] or 0,
                "failed": row["failed"] or 0,
                "queued": row["queued"] or 0,
            }
