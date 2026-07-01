from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    url: str


class ImportResponse(BaseModel):
    video_id: int
    status: str
    task_id: str
    message: str


class LocalScanResponse(BaseModel):
    imported: list[ImportResponse]
    skipped: list[str]
    watch_dir: str


class SourceVideoOut(BaseModel):
    id: int
    source_url: str
    caption_original: str | None
    raw_video_path: str | None
    duration: float | None
    status: str
    error_message: str | None

    model_config = {"from_attributes": True}


class SegmentOut(BaseModel):
    id: int
    start_time: float
    end_time: float
    text_cn: str
    text_vi: str | None
    text_vi_optimized: str | None
    voice_duration: float | None
    max_duration: float
    warning: bool


class SegmentUpdate(BaseModel):
    id: int
    text_vi: str | None = None
    text_vi_optimized: str | None = None


class SegmentUpdateRequest(BaseModel):
    segments: list[SegmentUpdate]


class SubtitleStyle(BaseModel):
    font_size: int = 18
    primary_color: str = "FFFFFF"
    outline_color: str = "000000"


class RenderRequest(BaseModel):
    tts_provider: str = "local"
    voice_id: str = "vi_default"
    original_audio_volume: float = Field(default=0.15, ge=0, le=1)
    voice_volume: float = Field(default=1.0, ge=0, le=2)
    burn_subtitles: bool = True
    subtitle_style: SubtitleStyle = SubtitleStyle()


class RenderJobOut(BaseModel):
    id: int
    video_id: int
    status: str
    progress_percentage: int
    output_video_path: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class CaptionOut(BaseModel):
    caption: str
    hashtags: list[str]


class CleanupOut(BaseModel):
    video_id: int
    deleted_files: int
    kept_files: int
