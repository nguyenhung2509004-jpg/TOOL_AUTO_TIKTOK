from datetime import datetime

from pydantic import BaseModel, Field


class TrendScanRequest(BaseModel):
    niche: str
    limit: int = Field(default=20, ge=1, le=100)


class AttachLocalFileRequest(BaseModel):
    file_path: str


class DouyinTrendOut(BaseModel):
    id: int
    video_id: str | None
    source_url: str
    author_name: str | None
    author_id: str | None
    caption: str | None
    cover_url: str | None
    like_count: int
    comment_count: int
    share_count: int
    collect_count: int
    duration: float | None
    create_time: int | None
    hot_score: float
    niche: str | None
    status: str
    waiting_download: bool
    waiting_since: datetime | None
    raw_video_path: str | None
    imported_file_name: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NicheOut(BaseModel):
    label_vi: str
    keyword_cn: str


class TrendActionResponse(BaseModel):
    trend: DouyinTrendOut
    message: str
