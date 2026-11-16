import time
from pathlib import Path
from typing import Dict, Any
from services.video_gateway.backends.base import VideoBackend, VideoGenerationResult
from app.core.logging import logger
from app.core.exceptions import BackendUnavailableException
from observability.metrics import (
    ML_INFERENCE_REQUESTS,
    ML_INFERENCE_LATENCY,
    ML_BACKEND_AVAILABILITY,
    ML_BACKEND_ERRORS,
)


class LocalCudaVideoBackend(VideoBackend):
    """
    Local PyTorch / Diffusers CogVideoX-2B Backend.
    Uses pipeline/cogvideo.py when run on a local workstation with an RTX 4060 GPU.
    """

    def __init__(self):
        self.model_id = "THUDM/CogVideoX-2b"
        self._generator = None
        self._check_cuda()

    def _check_cuda(self) -> bool:
        try:
            import torch
            available = torch.cuda.is_available()
            ML_BACKEND_AVAILABILITY.labels(backend="OPTIONAL_LOCAL").set(1 if available else 0)
            return available
        except Exception:
            ML_BACKEND_AVAILABILITY.labels(backend="OPTIONAL_LOCAL").set(0)
            return False

    def health_check(self) -> Dict[str, Any]:
        cuda_ok = self._check_cuda()
        return {
            "status": "GPU_AVAILABLE" if cuda_ok else "GPU_BACKEND_UNAVAILABLE",
            "backend": "OPTIONAL_LOCAL",
            "model_id": self.model_id,
            "cuda_available": cuda_ok,
            "is_mock": False,
            "message": "Local CUDA GPU available" if cuda_ok else "No local CUDA GPU detected. Switch to MOCK or REAL_REMOTE backend."
        }

    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        if not self._check_cuda():
            ML_BACKEND_ERRORS.labels(model="cogvideox-2b", backend="OPTIONAL_LOCAL", error_type="NO_CUDA").inc()
            raise BackendUnavailableException(
                "GPU_BACKEND_UNAVAILABLE: Local CUDA GPU required for OPTIONAL_LOCAL CogVideoX backend."
            )
            
        start_time = time.time()
        ML_INFERENCE_REQUESTS.labels(model="cogvideox-2b", backend="OPTIONAL_LOCAL").inc()
        
        try:
            from pipeline.cogvideo import CogVideoXGenerator
            if self._generator is None:
                self._generator = CogVideoXGenerator()
                if not self._generator._loaded:
                    self._generator.load_model()
                    
            output_path = Path(output_path)
            res_path = self._generator.generate_video_sync(
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
                num_inference_steps=num_inference_steps
            )
            
            latency = time.time() - start_time
            ML_INFERENCE_LATENCY.labels(model="cogvideox-2b", backend="OPTIONAL_LOCAL").observe(latency)
            
            return VideoGenerationResult(
                video_path=str(res_path),
                duration_seconds=round(latency, 2),
                backend="OPTIONAL_LOCAL",
                model_id=self.model_id,
                revision="diffusers-fp16",
                is_mock=False,
                metadata={
                    "prompt": prompt,
                    "frames": num_frames,
                    "steps": num_inference_steps
                }
            )
        except Exception as e:
            ML_BACKEND_ERRORS.labels(model="cogvideox-2b", backend="OPTIONAL_LOCAL", error_type=type(e).__name__).inc()
            logger.error(f"Local CogVideoX generation failed: {e}")
            raise
