from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChannelBase(BaseModel):
    id: str = Field(..., description="Unique alphanumeric channel identifier")
    name: str = Field(..., description="Display name for channel")
    niche: str = Field(..., description="Niche topic area")
    target_audience: Optional[str] = "general audience 18-35"
    tone: Optional[str] = "engaging, informative"
    search_keywords: Optional[List[str]] = Field(default_factory=list)
    reels_per_day: Optional[int] = 1
    content_rules: Optional[List[str]] = Field(default_factory=list)
    duration_seconds: Optional[int] = 60
    voice_preset: Optional[str] = "en-US-ChristopherNeural"
    caption_style: Optional[str] = "bold_white"
    kling_duration: Optional[int] = 5
    kling_mode: Optional[str] = "std"
    reel_style: Optional[str] = "documentary"


class ChannelCreateRequest(ChannelBase):
    pass


class ChannelUpdateRequest(BaseModel):
    name: Optional[str] = None
    niche: Optional[str] = None
    target_audience: Optional[str] = None
    tone: Optional[str] = None
    search_keywords: Optional[List[str]] = None
    reels_per_day: Optional[int] = None
    content_rules: Optional[List[str]] = None
    duration_seconds: Optional[int] = None
    voice_preset: Optional[str] = None
    caption_style: Optional[str] = None
    reel_style: Optional[str] = None
