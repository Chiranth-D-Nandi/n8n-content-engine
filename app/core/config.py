import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseModel):
    # Application Info
    APP_NAME: str = "Matiks Content Engine"
    APP_ENV: str = Field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    DEBUG: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    API_PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", os.getenv("API_PORT", "5000"))))
    API_HOST: str = Field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    
    # Security & CORS
    SECRET_KEY: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "matiks-insecure-dev-secret-key-change-in-prod"))
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]
    )
    DEMO_MODE: bool = Field(default_factory=lambda: os.getenv("DEMO_MODE", "true").lower() == "true")
    RATE_LIMIT_PER_MINUTE: int = Field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")))
    
    # Database
    DATABASE_PATH: str = Field(default_factory=lambda: os.getenv("DATABASE_PATH", str(BASE_DIR / "matiks.db")))
    
    # Redis & Celery
    REDIS_URL: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    CELERY_BROKER_URL: str = Field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0")))
    CELERY_RESULT_BACKEND: str = Field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/0")))
    CELERY_ALWAYS_EAGER: bool = Field(default_factory=lambda: os.getenv("CELERY_ALWAYS_EAGER", "false").lower() == "true")
    CELERY_TASK_TIMEOUT: int = Field(default_factory=lambda: int(os.getenv("CELERY_TASK_TIMEOUT", "1800")))
    
    # External APIs
    GEMINI_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    YOUTUBE_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY"))
    
    # ML Inference Services
    # Whisper BentoML Service URL
    WHISPER_SERVICE_URL: str = Field(default_factory=lambda: os.getenv("WHISPER_SERVICE_URL", "http://localhost:3000"))
    WHISPER_LOCAL_FALLBACK: bool = Field(default_factory=lambda: os.getenv("WHISPER_LOCAL_FALLBACK", "true").lower() == "true")
    
    # Video Generation Gateway
    # Backends: MOCK, REAL_REMOTE, OPTIONAL_LOCAL
    VIDEO_BACKEND: str = Field(default_factory=lambda: os.getenv("VIDEO_BACKEND", "MOCK").upper())
    ALLOW_VIDEO_FALLBACK: bool = Field(default_factory=lambda: os.getenv("ALLOW_VIDEO_FALLBACK", "true").lower() == "true")
    VIDEO_GATEWAY_URL: str = Field(default_factory=lambda: os.getenv("VIDEO_GATEWAY_URL", "http://localhost:8000"))
    HF_TOKEN: Optional[str] = Field(default_factory=lambda: os.getenv("HF_TOKEN", os.getenv("HUGGINGFACE_TOKEN")))
    HF_SPACE_URL: Optional[str] = Field(default_factory=lambda: os.getenv("HF_SPACE_URL"))
    
    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(default_factory=lambda: os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
    OTEL_SERVICE_NAME: str = Field(default_factory=lambda: os.getenv("OTEL_SERVICE_NAME", "n8n-content-engine"))
    PROMETHEUS_METRICS_ENABLED: bool = Field(default_factory=lambda: os.getenv("PROMETHEUS_METRICS_ENABLED", "true").lower() == "true")
    
    # Paths
    OUTPUT_DIR: Path = Field(default_factory=lambda: BASE_DIR / "outputs")
    TEMP_DIR: Path = Field(default_factory=lambda: BASE_DIR / "temp")
    
    class Config:
        arbitrary_types_allowed = True


settings = Settings()
