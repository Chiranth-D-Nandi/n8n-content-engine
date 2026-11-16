import os
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from services.video_gateway.backends.base import VideoBackend, VideoGenerationResult
from app.core.exceptions import BackendUnavailableException, QuotaExhaustedException
from app.core.logging import logger
from app.core.config import settings
from observability.metrics import (
    ML_INFERENCE_REQUESTS,
    ML_INFERENCE_LATENCY,
    ML_BACKEND_AVAILABILITY,
    ML_BACKEND_ERRORS,
    GPU_QUOTA_REMAINING,
)


class RemoteGpuVideoBackend(VideoBackend):
    """
    Real Remote Video Inference Backend targeting Hugging Face Spaces ZeroGPU.
    
    ZeroGPU Specs:
    - 48GB VRAM (half RTX Pro 6000 Blackwell)
    - 5 GPU-minutes free per day
    - Zero cost, no credit card required
    """

    def __init__(self, endpoint_url: Optional[str] = None, api_token: Optional[str] = None):
        self.endpoint_url = (endpoint_url or settings.HF_SPACE_URL or "").rstrip("/")
        self.api_token = api_token or settings.HF_TOKEN
        self.model_id = "THUDM/CogVideoX-2b"
        self._gradio_client = None
        self._quota_exceeded = False
        self._quota_reset_time = 0

    def _get_client(self):
        if not self.endpoint_url:
            return None
        if self._gradio_client is None:
            try:
                from gradio_client import Client
                self._gradio_client = Client(self.endpoint_url, hf_token=self.api_token)
            except Exception as e:
                logger.warning(f"Failed to instantiate gradio_client for {self.endpoint_url}: {e}")
                self._gradio_client = None
        return self._gradio_client

    def health_check(self) -> Dict[str, Any]:
        if not self.endpoint_url:
            ML_BACKEND_AVAILABILITY.labels(backend="REAL_REMOTE").set(0)
            return {
                "status": "GPU_BACKEND_UNAVAILABLE",
                "backend": "REAL_REMOTE",
                "is_mock": False,
                "message": "HF_SPACE_URL is not configured. Set HF_SPACE_URL in environment.",
                "quota_status": "UNCONFIGURED"
            }

        # Check if currently in quota penalty window
        if self._quota_exceeded and time.time() < self._quota_reset_time:
            ML_BACKEND_AVAILABILITY.labels(backend="REAL_REMOTE").set(0)
            GPU_QUOTA_REMAINING.labels(provider="huggingface_zerogpu").set(0)
            remaining_sec = int(self._quota_reset_time - time.time())
            return {
                "status": "QUOTA_EXHAUSTED",
                "backend": "REAL_REMOTE",
                "is_mock": False,
                "message": f"ZeroGPU 5 min/day quota exhausted. Resets in {remaining_sec // 3600}h {(remaining_sec % 3600) // 60}m.",
                "quota_status": "EXHAUSTED",
                "retry_after_seconds": remaining_sec
            }

        try:
            res = requests.get(self.endpoint_url, timeout=5.0)
            is_alive = res.status_code in [200, 302]
            ML_BACKEND_AVAILABILITY.labels(backend="REAL_REMOTE").set(1 if is_alive else 0)
            GPU_QUOTA_REMAINING.labels(provider="huggingface_zerogpu").set(100)
            return {
                "status": "GPU_AVAILABLE" if is_alive else "GPU_BACKEND_UNAVAILABLE",
                "backend": "REAL_REMOTE",
                "is_mock": False,
                "endpoint": self.endpoint_url,
                "model_id": self.model_id,
                "hardware": "ZeroGPU 48GB (RTX Pro 6000)",
                "quota_status": "AVAILABLE"
            }
        except Exception:
            ML_BACKEND_AVAILABILITY.labels(backend="REAL_REMOTE").set(0)
            return {
                "status": "GPU_BACKEND_UNAVAILABLE",
                "backend": "REAL_REMOTE",
                "is_mock": False,
                "message": "ZeroGPU Space is sleeping or unreachable."
            }

    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        if not self.endpoint_url:
            raise BackendUnavailableException(
                "GPU_BACKEND_UNAVAILABLE: HF_SPACE_URL not configured. "
                "Set your ZeroGPU Space URL or switch VIDEO_BACKEND=MOCK."
            )

        # CogVideoX-2B prompt length constraint: maximum 226 tokens
        words = prompt.split()
        if len(words) > 200:
            prompt = " ".join(words[:200])

        start_time = time.time()
        ML_INFERENCE_REQUESTS.labels(model="cogvideox-2b", backend="REAL_REMOTE").inc()
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[REAL_REMOTE] Calling HF ZeroGPU Space ({self.endpoint_url}) "
            f"prompt='{prompt[:60]}...' (steps={num_inference_steps}, frames={num_frames})"
        )

        client = self._get_client()
        if client is not None:
            try:
                # Call Gradio Space API
                job = client.submit(
                    prompt,
                    num_frames,
                    num_inference_steps,
                    api_name="/generate_reel_video"
                )
                
                # Poll status
                while not job.done():
                    time.sleep(2)
                    status = job.status()
                    logger.debug(f"[ZeroGPU] Status: {status.code}")

                video_result_path = job.result()
                if video_result_path and Path(video_result_path).exists():
                    shutil.copy2(video_result_path, output_path)
                else:
                    raise RuntimeError(f"Gradio ZeroGPU returned invalid path: {video_result_path}")

                latency = time.time() - start_time
                ML_INFERENCE_LATENCY.labels(model="cogvideox-2b", backend="REAL_REMOTE").observe(latency)
                self._quota_exceeded = False

                return VideoGenerationResult(
                    video_path=str(output_path),
                    duration_seconds=round(latency, 2),
                    backend="REAL_REMOTE",
                    model_id=self.model_id,
                    revision="zerogpu-48gb",
                    is_mock=False,
                    metadata={
                        "prompt": prompt,
                        "frames": num_frames,
                        "steps": num_inference_steps,
                        "endpoint": self.endpoint_url
                    }
                )

            except Exception as e:
                err_str = str(e).lower()
                if "quota" in err_str or "exceeded" in err_str:
                    self._quota_exceeded = True
                    self._quota_reset_time = time.time() + (24 * 3600)
                    GPU_QUOTA_REMAINING.labels(provider="huggingface_zerogpu").set(0)
                    ML_BACKEND_ERRORS.labels(model="cogvideox-2b", backend="REAL_REMOTE", error_type="QUOTA_EXHAUSTED").inc()
                    raise QuotaExhaustedException(
                        "QUOTA_EXHAUSTED: Daily 5-minute Hugging Face ZeroGPU quota exceeded. "
                        "Quota resets in 24 hours. The job has been halted gracefully."
                    )
                else:
                    ML_BACKEND_ERRORS.labels(model="cogvideox-2b", backend="REAL_REMOTE", error_type=type(e).__name__).inc()
                    raise BackendUnavailableException(
                        f"GPU_BACKEND_UNAVAILABLE: Remote ZeroGPU inference failed ({e})."
                    )

        # Fallback raw HTTP request to custom GPU endpoint
        try:
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            response = requests.post(
                f"{self.endpoint_url}/generate",
                json={"prompt": prompt, "num_frames": num_frames, "num_inference_steps": num_inference_steps},
                headers=headers,
                timeout=300.0
            )
            if response.status_code == 429:
                raise QuotaExhaustedException("QUOTA_EXHAUSTED: Remote GPU inference quota reached.")
            elif response.status_code != 200:
                raise BackendUnavailableException(f"Remote GPU error {response.status_code}: {response.text}")

            output_path.write_bytes(response.content)
            latency = time.time() - start_time
            ML_INFERENCE_LATENCY.labels(model="cogvideox-2b", backend="REAL_REMOTE").observe(latency)
            
            return VideoGenerationResult(
                video_path=str(output_path),
                duration_seconds=round(latency, 2),
                backend="REAL_REMOTE",
                model_id=self.model_id,
                revision="remote-http",
                is_mock=False,
                metadata={"prompt": prompt, "endpoint": self.endpoint_url}
            )
        except Exception as ex:
            raise BackendUnavailableException(f"GPU_BACKEND_UNAVAILABLE: {ex}")
