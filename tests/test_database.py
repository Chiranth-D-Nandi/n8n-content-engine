import pytest
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobStatus, PipelineStage


def test_job_repository_crud(job_repo):
    # 1. Create job
    job = job_repo.create_job(
        job_id="test_job_101",
        channel_id="ai_tech",
        payload={"reel_count": 1}
    )
    assert job["job_id"] == "test_job_101"
    assert job["status"] == "queued"

    # 2. Update status and stage
    job_repo.update_job_status(
        job_id="test_job_101",
        status=JobStatus.RUNNING,
        stage=PipelineStage.RESEARCH,
        progress=20
    )
    job = job_repo.get_job("test_job_101")
    assert job["status"] == "running"
    assert job["stage"] == "research"
    assert job["progress"] == 20

    # 3. Record stage
    job_repo.record_stage("test_job_101", "research", "complete", duration_seconds=1.5)
    job = job_repo.get_job("test_job_101")
    assert len(job["stages"]) == 1
    assert job["stages"][0]["stage_name"] == "research"
    assert job["stages"][0]["duration_seconds"] == 1.5

    # 4. Complete job
    job_repo.complete_job(
        job_id="test_job_101",
        outputs=[{"topic": "Test Topic", "file": "outputs/reel.mp4", "size_mb": 5.2}],
        failed_reels=[],
        duration_seconds=12.5,
        backend_used="MOCK"
    )
    job = job_repo.get_job("test_job_101")
    assert job["status"] == "complete"
    assert len(job["outputs"]) == 1
    assert job["duration_seconds"] == 12.5

    # 5. Check stats
    stats = job_repo.get_stats()
    assert stats["jobs"] >= 1
    assert stats["complete"] >= 1
