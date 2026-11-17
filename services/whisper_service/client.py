import os
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logging import logger
from observability.metrics import (
    ML_INFERENCE_REQUESTS,
    ML_INFERENCE_LATENCY,
    ML_BACKEND_ERRORS,
)


class WhisperClient:
    """
    Client for the dedicated Whisper BentoML Inference Service.
    Communicates over HTTP, recording Prometheus metrics and falling
    back safely if configured.
    """

    def __init__(self, service_url: Optional[str] = None):
        self.service_url = (service_url or settings.WHISPER_SERVICE_URL).rstrip("/")
        self._local_model = None

    def is_service_healthy(self) -> bool:
        try:
            res = requests.get(f"{self.service_url}/health", timeout=2.0)
            return res.status_code == 200
        except Exception:
            return False

    def transcribe(self, audio_path: Path, language: str = "en", text_hint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Sends audio to the Whisper BentoML service over HTTP.
        If unavailable, uses low-memory alignment or local faster-whisper.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        start_time = time.time()
        
        # Check remote BentoML service first
        if self.is_service_healthy():
            ML_INFERENCE_REQUESTS.labels(model="whisper", backend="bentoml").inc()
            try:
                with open(audio_path, "rb") as f:
                    files = {"audio_file": (audio_path.name, f, "audio/mpeg")}
                    data = {"language": language}
                    response = requests.post(
                        f"{self.service_url}/transcribe",
                        files=files,
                        data=data,
                        timeout=60.0
                    )
                if response.status_code == 200:
                    result = response.json()
                    latency = time.time() - start_time
                    ML_INFERENCE_LATENCY.labels(model="whisper", backend="bentoml").observe(latency)
                    words = result.get("words", [])
                    logger.info(f"Whisper BentoML transcribed {len(words)} words in {latency:.2f}s")
                    return words
            except Exception as e:
                logger.warning(f"Whisper BentoML failed ({e}), falling back...")

        # In low-memory environments (e.g. Render 512MB free tier), generate aligned timestamps
        # directly from the script text and audio duration to avoid OOM killing the process
        if getattr(settings, "LOW_MEMORY_MODE", True) or os.getenv("RENDER"):
            logger.info("Using low-memory timestamp alignment (zero PyTorch RAM overhead)...")
            duration = self._get_audio_duration(audio_path)
            words = self._synthesize_word_timestamps(text_hint or "Amazing content for your daily reel", duration)
            latency = time.time() - start_time
            ML_INFERENCE_LATENCY.labels(model="whisper", backend="aligned_fallback").observe(latency)
            return words

        # Standard local faster-whisper fallback (for machines with >=4GB RAM)
        if settings.WHISPER_LOCAL_FALLBACK:
            return self._transcribe_local_fallback(audio_path, language)
        return []

    def _get_audio_duration(self, audio_path: Path) -> float:
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return max(float(res.stdout.strip()), 1.0)
        except Exception:
            return 8.0

    def _synthesize_word_timestamps(self, text: str, duration: float) -> List[Dict[str, Any]]:
        import re
        tokens = [w.strip() for w in re.split(r"\s+", text) if w.strip()]
        if not tokens:
            return []
        step = max(duration / len(tokens), 0.1)
        result = []
        for i, word in enumerate(tokens):
            start = round(i * step, 2)
            end = round(min((i + 1) * step, duration), 2)
            result.append({"text": word, "start": start, "end": end})
        return result

    def _transcribe_local_fallback(self, audio_path: Path, language: str = "en") -> List[Dict[str, Any]]:
        """
        Local in-memory fallback for local development or when BentoML container is not spun up.
        Reuses a single model instance rather than instantiating on every request.
        """
        start_time = time.time()
        ML_INFERENCE_REQUESTS.labels(model="whisper", backend="local_fallback").inc()
        
        try:
            os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
            from faster_whisper import WhisperModel
            if self._local_model is None:
                logger.info("Initializing fallback local faster-whisper model (singleton)...")
                self._local_model = WhisperModel("base", device="cpu", compute_type="int8")
                
            segments, info = self._local_model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language=language
            )
            
            words = []
            for segment in segments:
                if segment.words is None:
                    continue
                for word in segment.words:
                    cleaned = word.word.strip()
                    if cleaned:
                        words.append({
                            "text": cleaned,
                            "start": round(word.start, 3),
                            "end": round(word.end, 3)
                        })
                        
            latency = time.time() - start_time
            ML_INFERENCE_LATENCY.labels(model="whisper", backend="local_fallback").observe(latency)
            logger.info(f"Local Whisper fallback transcribed {len(words)} words in {latency:.2f}s")
            return words
            
        except Exception as err:
            ML_BACKEND_ERRORS.labels(model="whisper", backend="local_fallback", error_type=type(err).__name__).inc()
            logger.error(f"Local Whisper fallback failed: {err}")
            return []
