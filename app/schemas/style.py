from typing import Optional
from pydantic import BaseModel, Field


class SubtitleStyleModel(BaseModel):
    font: str = "Arial Black"
    font_size: int = 80
    primary_color: str = "#FFFFFF"
    stroke_color: Optional[str] = "#000000"
    stroke_width: Optional[int] = 4
    position: Optional[str] = "center"  # top, center, bottom
    bold: Optional[bool] = True
    italic: Optional[bool] = False


class StyleCreateRequest(BaseModel):
    name: str = Field(..., description="Unique style preset identifier")
    style: SubtitleStyleModel
