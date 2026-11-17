import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
from services.video_gateway.backends.base import VideoBackend, VideoGenerationResult
from app.core.logging import logger
from observability.metrics import (
    ML_INFERENCE_REQUESTS,
    ML_INFERENCE_LATENCY,
    ML_BACKEND_AVAILABILITY,
)


class MockVideoBackend(VideoBackend):
    """
    Mock Video Backend for CI/CD, testing, and benchmark scenarios.
    
    CRITICAL DISCLAIMER:
    This is an explicitly simulated backend. It does NOT execute CogVideoX-2B neural weights
    and MUST NEVER be reported as real model inference.
    """

    def __init__(self, simulated_delay_seconds: float = 1.0):
        self.simulated_delay = simulated_delay_seconds
        ML_BACKEND_AVAILABILITY.labels(backend="MOCK").set(1)

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "available",
            "backend": "MOCK",
            "is_mock": True,
            "message": "Mock inference engine active for reproducible test & verification."
        }

    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        logger.warning(
            f"[MOCK_INFERENCE] Generating simulated reel background for prompt: '{prompt[:60]}...'"
        )
        start_time = time.time()
        ML_INFERENCE_REQUESTS.labels(model="cogvideox-2b", backend="MOCK").inc()
        
        # Simulate inference time if configured
        if self.simulated_delay > 0:
            time.sleep(self.simulated_delay)
            
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if an existing sample reel exists in outputs to use as video asset
        sample_candidates = list(Path("outputs").glob("*/*.mp4"))
        if sample_candidates and sample_candidates[0] != output_path:
            shutil.copy2(sample_candidates[0], output_path)
        else:
            # Generate a minimal valid 1080x1920 MP4 canvas using ultrafast stillimage
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=0x111625:s=1080x1920:d=15:r=24",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                str(output_path.resolve())
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            except Exception as e:
                logger.warning(f"FFmpeg mock generator failed ({e}), retrying with fallback format...")
                cmd_fb = [
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "color=c=black:s=720x1280:d=10:r=20",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    str(output_path.resolve())
                ]
                subprocess.run(cmd_fb, check=True, capture_output=True, timeout=60)
                
        latency = time.time() - start_time
        ML_INFERENCE_LATENCY.labels(model="cogvideox-2b", backend="MOCK").observe(latency)
        
        return VideoGenerationResult(
            video_path=str(output_path),
            duration_seconds=round(latency, 3),
            backend="MOCK",
            model_id="simulated-cogvideox-2b",
            revision="mock-v1.0",
            is_mock=True,
            metadata={
                "prompt": prompt,
                "frames": num_frames,
                "steps": num_inference_steps,
                "simulated_delay": self.simulated_delay
            }
        )
