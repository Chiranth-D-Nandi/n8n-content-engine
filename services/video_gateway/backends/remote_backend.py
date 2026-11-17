import os
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from services.video_gateway.backends.base import VideoBackend, VideoGenerationResult
from services.video_gateway.video_failover_router import VideoFailoverOrchestrator, is_space_awake
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
    Features multi-tier failover orchestration across live ZeroGPU endpoints,
    descending reservation quota packing, and zero-RAM file streaming.
    """

    def __init__(self, endpoint_url: Optional[str] = None, api_token: Optional[str] = None):
        self.endpoint_url = (endpoint_url or settings.HF_SPACE_URL or "https://lightricks-ltx-2-3.hf.space").rstrip("/")
        self.api_token = api_token or settings.HF_TOKEN
        self.model_id = "Lightricks/LTX-2.3-ZeroGPU"
        self._orchestrator = VideoFailoverOrchestrator(
            hf_token=self.api_token,
            bigmodel_api_key=os.getenv("BIGMODEL_API_KEY"),
            kaggle_worker_url=os.getenv("KAGGLE_WORKER_URL"),
            pexels_api_key=os.getenv("PEXELS_API_KEY"),
        )

    def health_check(self) -> Dict[str, Any]:
        # Fast pre-flight check across top ZeroGPU endpoints
        primary_spaces = ["Lightricks/LTX-2-3", "Upsampler/wan-2-2-14b-text-to-video", "Upsampler/ltx-video"]
        is_alive = any(is_space_awake(sp) for sp in primary_spaces)

        ML_BACKEND_AVAILABILITY.labels(backend="REAL_REMOTE").set(1 if is_alive else 0)
        GPU_QUOTA_REMAINING.labels(provider="huggingface_zerogpu").set(100 if is_alive else 0)
        return {
            "status": "GPU_AVAILABLE" if is_alive else "GPU_BACKEND_UNAVAILABLE",
            "backend": "REAL_REMOTE",
            "is_mock": False,
            "endpoint": "https://lightricks-ltx-2-3.hf.space (Multi-Tier Cascade)",
            "model_id": self.model_id,
            "hardware": "ZeroGPU 48GB (RTX Pro 6000 Blackwell)",
            "quota_status": "AVAILABLE" if is_alive else "SLEEPING_OR_QUEUED",
        }

    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        # Prompt length constraint: maximum 200 tokens
        words = prompt.split()
        if len(words) > 200:
            prompt = " ".join(words[:200])

        start_time = time.time()
        ML_INFERENCE_REQUESTS.labels(model="cogvideox-2b", backend="REAL_REMOTE").inc()
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[REAL_REMOTE] Invoking cloud ZeroGPU failover cascade for prompt='{prompt[:60]}...'"
        )

        res = self._orchestrator.generate(
            prompt=prompt,
            output_path=output_path,
            duration_s=5.0,
            seed=42,
        )

        if res.get("status") == "ok" and output_path.exists() and output_path.stat().st_size > 10_000:
            latency = time.time() - start_time
            ML_INFERENCE_LATENCY.labels(model="cogvideox-2b", backend="REAL_REMOTE").observe(latency)
            provider = res.get("provider", "cloud_zerogpu")
            logger.info(f"[REAL_REMOTE] Video successfully generated via {provider} in {latency:.2f}s!")
            return VideoGenerationResult(
                video_path=str(output_path),
                duration_seconds=round(latency, 2),
                backend="REAL_REMOTE",
                model_id=provider,
                revision="zerogpu-48gb-blackwell",
                is_mock=False,
                metadata=res,
            )
        else:
            attempts = res.get("attempts", [])
            err_msg = f"ZeroGPU cascade was unable to produce video (status={res.get('status')}). Attempts: {attempts}"
            logger.warning(f"[REAL_REMOTE] {err_msg}")
            ML_BACKEND_ERRORS.labels(model="cogvideox-2b", backend="REAL_REMOTE", error_type="AllEndpointsFailed").inc()
            raise BackendUnavailableException(f"GPU_BACKEND_UNAVAILABLE: {err_msg}")

