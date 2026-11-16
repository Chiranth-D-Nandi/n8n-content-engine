from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel


class VideoGenerationResult(BaseModel):
    video_path: str
    duration_seconds: float
    backend: str
    model_id: str
    revision: Optional[str] = None
    is_mock: bool = False
    metadata: Dict[str, Any] = {}


class VideoBackend(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        **kwargs
    ) -> VideoGenerationResult:
        """
        Generate video from prompt.
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Check backend health and availability.
        """
        pass
