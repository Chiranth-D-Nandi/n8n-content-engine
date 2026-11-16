import pytest
from unittest.mock import patch, MagicMock
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobStatus, PipelineStage


def test_job_submission_validation(client):
    # Missing channel_id
    res = client.post("/webhook/matiks-reel", json={})
    assert res.status_code == 400
    assert "channel_id" in res.get_json()["error"]


def test_job_submission_and_lifecycle(client):
    # Mock the Celery task delay so it registers job without running real external APIs
    with patch("app.services.job_service.generate_reel_pipeline_task.delay") as mock_delay:
        payload = {
            "channel_id": "ai_tech",
            "topic_override": "Automated Unit Test Reel",
            "reel_count": 1,
            "subtitle_style": {
                "font": "Arial",
                "font_size": 50,
                "primary_color": "#FFFFFF",
                "position": "center"
            }
        }
        
        # 1. Submit Job
        res = client.post("/webhook/matiks-reel", json=payload)
        assert res.status_code == 202
        data = res.get_json()
        assert "job_id" in data
        job_id = data["job_id"]
        assert data["status"] == "queued"
        assert f"/jobs/{job_id}" in data["poll_url"]
        assert mock_delay.called

        # 2. Get Job Details while queued
        res = client.get(f"/jobs/{job_id}")
        assert res.status_code == 200
        job_data = res.get_json()
        assert job_data["job_id"] == job_id
        assert job_data["channel_id"] == "ai_tech"
        assert job_data["status"] == "queued"

        # 3. Simulate job completion by repo
        from app.core.config import settings
        repo = JobRepository(settings.DATABASE_PATH)
        repo.update_job_status(job_id, JobStatus.RUNNING, PipelineStage.VIDEO, progress=60)
        repo.complete_job(
            job_id=job_id,
            outputs=[{"topic": "Automated Unit Test Reel", "file": "outputs/ai_tech/reel_1.mp4", "size_mb": 4.5}],
            failed_reels=[],
            duration_seconds=8.2,
            backend_used="MOCK"
        )

        # 4. Check /status/<job_id> backward compatibility
        res = client.get(f"/status/{job_id}")
        assert res.status_code == 200
        status_data = res.get_json()
        assert status_data["job_id"] == job_id
        assert status_data["status"] == "complete"
        assert "reel_1.mp4" in status_data["output_path"]

        # 5. List jobs
        res = client.get("/jobs?limit=5")
        assert res.status_code == 200
        jobs_list = res.get_json()
        assert any(j["job_id"] == job_id for j in jobs_list)
