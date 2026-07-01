from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SourceVideo(Base):
    __tablename__ = "source_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), default="douyin")
    source_url: Mapped[str] = mapped_column(Text)
    source_video_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    caption_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    segments: Mapped[list["VideoSegment"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    render_jobs: Mapped[list["RenderJob"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class VideoSegment(Base):
    __tablename__ = "video_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("source_videos.id", ondelete="CASCADE"), index=True)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text_cn: Mapped[str] = mapped_column(Text)
    text_vi: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_vi_optimized: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_segment_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    display_order: Mapped[int] = mapped_column(Integer)

    video: Mapped[SourceVideo] = relationship(back_populates="segments")


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("source_videos.id", ondelete="CASCADE"), index=True)
    tts_provider: Mapped[str] = mapped_column(String(50))
    voice_id: Mapped[str] = mapped_column(String(100))
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_audio_volume: Mapped[float] = mapped_column(Float, default=0.15)
    voice_volume: Mapped[float] = mapped_column(Float, default=1.0)
    burn_subtitles: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    video: Mapped[SourceVideo] = relationship(back_populates="render_jobs")


class DouyinTrend(Base):
    __tablename__ = "douyin_trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    collect_count: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    create_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hot_score: Mapped[float] = mapped_column(Float, default=0)
    niche: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="found")
    waiting_download: Mapped[bool] = mapped_column(Boolean, default=False)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
