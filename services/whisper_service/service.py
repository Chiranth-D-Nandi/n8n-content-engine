import os
import time
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import bentoml
from pydantic import BaseModel

# Input and Output schemas
class WordTimestamp(BaseModel):
    text: str
    start: float
    end: float


class TranscriptionRequest(BaseModel):
    language: str = "en"
    word_timestamps: bool = True


class TranscriptionResponse(BaseModel):
    words: List[WordTimestamp]
    execution_time_seconds: float
    language: str
    model: str = "faster-whisper-base-int8"


@bentoml.service(
    name="whisper_service",
    resources={"cpu": "2"},
    traffic={"timeout": 60}
)
class WhisperService:
    def __init__(self):
        print("[Whisper BentoML] Loading faster-whisper 'base' model into memory once...")
        start_t = time.time()
        from faster_whisper import WhisperModel
        # Load model once on startup and reuse
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        self.load_duration = time.time() - start_t
        print(f"[Whisper BentoML] Model loaded successfully in {self.load_duration:.2f}s ✅")

    @bentoml.api
    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "model": "faster-whisper-base",
            "device": "cpu",
            "load_duration": self.load_duration,
        }

    @bentoml.api
    def transcribe(
        self,
        audio_file: bentoml.Path,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Transcribe audio file and return word-level timestamps.
        """
        start_t = time.time()
        
        segments, info = self.model.transcribe(
            str(audio_file),
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
                    
        elapsed = time.time() - start_t
        print(f"[Whisper BentoML] Transcribed {len(words)} words in {elapsed:.2f}s")
        return {
            "words": words,
            "execution_time_seconds": round(elapsed, 3),
            "language": info.language if hasattr(info, "language") else language,
            "model": "faster-whisper-base-int8"
        }
