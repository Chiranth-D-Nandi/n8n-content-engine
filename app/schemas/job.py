from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(str, Enum):
    INIT = "init"
    RESEARCH = "research"
    SCRIPT = "script"
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLES = "subtitles"
    COMPOSITION = "composition"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreateRequest(BaseModel):
    channel_id: str = Field(..., description="Target channel or genre ID")
    topic_override: Optional[str] = Field(default="", description="Specific topic to pin generation")
    reel_count: Optional[int] = Field(default=1, ge=1, le=5, description="Number of reels to generate")
    subtitle_style: Optional[Dict[str, Any]] = Field(default=None, description="Custom subtitle styling parameters")


class ReelOutput(BaseModel):
    topic: str
    file: str
    size_mb: float = 0.0
    errors: List[str] = Field(default_factory=list)


class StageDetail(BaseModel):
    stage: str
    status: str
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: Optional[str] = PipelineStage.INIT
    progress: int = 0
    channel_id: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    payload: Optional[Dict[str, Any]] = None
    outputs: List[ReelOutput] = Field(default_factory=list)
    failed_reels: List[Dict[str, Any]] = Field(default_factory=list)
    stages: List[StageDetail] = Field(default_factory=list)
    error: Optional[str] = None
    error_type: Optional[str] = None
    backend_used: Optional[str] = None
    poll_url: Optional[str] = None
