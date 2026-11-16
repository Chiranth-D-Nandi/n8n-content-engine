from typing import Dict, Any, Optional
from pathlib import Path
from services.video_gateway.backends.base import VideoBackend, VideoGenerationResult
from services.video_gateway.backends.mock_backend import MockVideoBackend
from services.video_gateway.backends.remote_backend import RemoteGpuVideoBackend
from services.video_gateway.backends.local_backend import LocalCudaVideoBackend
from app.core.config import settings
from app.core.logging import logger


class VideoGenerationGateway:
    """
    Central Video Generation Gateway.
    Pluggable backend selector: MOCK, REAL_REMOTE, OPTIONAL_LOCAL.
    """

    def __init__(self, backend_type: Optional[str] = None):
        self.backend_type = (backend_type or settings.VIDEO_BACKEND).upper()
        self._backend: VideoBackend = self._init_backend()

    def _init_backend(self) -> VideoBackend:
        logger.info(f"[VideoGateway] Initializing backend: {self.backend_type}")
        if self.backend_type == "MOCK":
            return MockVideoBackend()
        elif self.backend_type == "REAL_REMOTE":
            return RemoteGpuVideoBackend()
        elif self.backend_type == "OPTIONAL_LOCAL":
            return LocalCudaVideoBackend()
        else:
            logger.warning(
                f"[VideoGateway] Unknown backend '{self.backend_type}'. Falling back to MOCK."
            )
            return MockVideoBackend()

    def get_status(self) -> Dict[str, Any]:
        return self._backend.health_check()

    def generate_video(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        return self._backend.generate(
            prompt=prompt,
            output_path=output_path,
            num_frames=num_frames,
            num_inference_steps=num_inference_steps,
            **kwargs
        )
