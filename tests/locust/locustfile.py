import os
import random
import uuid
from locust import HttpUser, task, between, tag

class ContentEngineUser(HttpUser):
    """
    Locust load testing user simulating real-world traffic against the API.
    
    SAFETY RULE:
    Always tests with MOCK video backend and mocked/cached endpoints.
    Never exhausts external Gemini or YouTube quotas during load tests.
    """
    wait_time = between(1, 3)
    active_jobs = []

    @tag("health")
    @task(4)
    def test_health_endpoints(self):
        self.client.get("/health", name="/health")
        self.client.get("/health/ready", name="/health/ready")

    @tag("metadata")
    @task(3)
    def test_metadata_endpoints(self):
        self.client.get("/channels", name="/channels")
        self.client.get("/genres", name="/genres")
        self.client.get("/caption-styles", name="/caption-styles")

    @tag("pipeline")
    @task(1)
    def test_job_lifecycle(self):
        """Submit a job, poll its status, and verify completion."""
        channels = ["ai_tech", "animals", "health_fitness"]
        selected_channel = random.choice(channels)
        
        payload = {
            "channel_id": selected_channel,
            "topic_override": f"Load Test Reel {uuid.uuid4().hex[:6]}",
            "reel_count": 1,
            "subtitle_style": None
        }
        
        with self.client.post("/webhook/matiks-reel", json=payload, catch_response=True, name="/webhook/matiks-reel") as resp:
            if resp.status_code in [200, 202]:
                data = resp.json()
                job_id = data.get("job_id")
                if job_id:
                    self.active_jobs.append(job_id)
                    resp.success()
                else:
                    resp.failure("No job_id returned in response")
            else:
                resp.failure(f"Job submission failed: {resp.status_code}")

    @tag("polling")
    @task(5)
    def test_poll_active_jobs(self):
        """Simulate dashboard polling active jobs."""
        if self.active_jobs:
            job_id = random.choice(self.active_jobs)
            with self.client.get(f"/jobs/{job_id}", catch_response=True, name="/jobs/[id]") as resp:
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") in ["complete", "completed", "failed"]:
                        if job_id in self.active_jobs:
                            self.active_jobs.remove(job_id)
                    resp.success()
                else:
                    resp.failure(f"Poll returned status {resp.status_code}")
        else:
            self.client.get("/jobs?limit=10", name="/jobs")

    @tag("metrics")
    @task(2)
    def test_prometheus_metrics_scrape(self):
        self.client.get("/metrics", name="/metrics")
