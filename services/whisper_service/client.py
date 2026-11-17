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

    def transcribe(self, audio_path: Path, language: str = "en") -> List[Dict[str, Any]]:
        """
        Sends audio to the Whisper BentoML service over HTTP.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        start_time = time.time()
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
            else:
                logger.warning(
                    f"Whisper BentoML returned status {response.status_code}: {response.text}"
                )
                raise RuntimeError(f"Whisper service error: {response.status_code}")

        except Exception as e:
            ML_BACKEND_ERRORS.labels(model="whisper", backend="bentoml", error_type=type(e).__name__).inc()
            logger.warning(f"Whisper BentoML service call failed ({e}). Checking local fallback...")
            
            if settings.WHISPER_LOCAL_FALLBACK:
                return self._transcribe_local_fallback(audio_path, language)
            raise

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
