from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Evidence(BaseModel):
    source: str
    excerpt: str
    reason: str


class ModuleFinding(BaseModel):
    module_id: str
    module_name: str
    target: str
    risk_level: RiskLevel = RiskLevel.low
    risk_score: float = 0.0
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AnalysisInput(BaseModel):
    video_id: str = "demo-video"
    title: str = ""
    description: str = ""
    speech_text: str = ""
    bullet_chats: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    visual_descriptions: list[str] = Field(default_factory=list)
    audio_cues: list[str] = Field(default_factory=list)
    ocr_text: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UrlFetchRequest(BaseModel):
    source_url: str
    max_comments: int = Field(default=20, ge=1, le=100)
    download_video: bool = False
    process_video: bool = True
    frame_interval_seconds: float = Field(default=4.0, ge=1.0, le=30.0)
    max_frames: int = Field(default=6, ge=1, le=24)
    whisper_model: str = "tiny"
    asr_model_path: str | None = None


class PreprocessedContent(BaseModel):
    request_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input_payload: AnalysisInput
    upload_path: str | None = None
    combined_text: str = ""
    comment_corpus: str = ""
    normalized_segments: dict[str, list[str]] = Field(default_factory=dict)
    standardized_metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisOutput(BaseModel):
    request_id: str
    created_at: str
    overall_risk_level: RiskLevel
    overall_risk_score: float
    summary: str
    module_findings: list[ModuleFinding]
    recommendations: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    execution_trace: list[str] = Field(default_factory=list)


class ModuleProfile(BaseModel):
    module_id: str
    module_name: str
    module_group: str
    detection_goal: str


class VideoFrameSample(BaseModel):
    timestamp_seconds: float
    image_path: str
    image_url: str | None = None
    ocr_text: list[str] = Field(default_factory=list)


class VideoProcessingSummary(BaseModel):
    enabled: bool = False
    completed: bool = False
    asr_completed: bool = False
    ocr_completed: bool = False
    whisper_model: str | None = None
    asr_backend: str | None = None
    speech_source: str | None = None
    audio_event_backend: str | None = None
    asr_language: str | None = None
    frame_interval_seconds: float | None = None
    frame_strategy: str | None = None
    extracted_frame_count: int = 0
    ocr_line_count: int = 0
    speech_text_length: int = 0
    asr_segment_count: int = 0
    audio_event_count: int = 0
    audio_path: str | None = None
    audio_asset_url: str | None = None
    notes: list[str] = Field(default_factory=list)
    frames: list[VideoFrameSample] = Field(default_factory=list)


class SourceFetchSummary(BaseModel):
    platform: str
    source_url: str
    aweme_id: str
    title: str = ""
    author_nickname: str = ""
    desc: str = ""
    cover_url: str | None = None
    publish_time: str | None = None
    video_downloaded: bool = False
    video_path: str | None = None
    video_asset_url: str | None = None
    video_download_error: str | None = None
    video_play_url: str | None = None
    comment_count_fetched: int = 0
    comment_total_reported: int | None = None
    video_processing: VideoProcessingSummary | None = None


class UrlFetchResponse(BaseModel):
    source: SourceFetchSummary
    input_payload: AnalysisInput
