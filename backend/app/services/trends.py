import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.video import DouyinTrend
from app.services.douyin_provider import NormalizedDouyinVideo


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def calculate_hot_score(
    like_count: int,
    comment_count: int,
    share_count: int,
    collect_count: int,
    create_time: int | None,
) -> float:
    engagement_score = like_count * 0.3 + comment_count * 0.8 + share_count * 1.2 + collect_count * 0.6
    if create_time:
        age_hours = max((time.time() - create_time) / 3600, 0)
    else:
        age_hours = 24
    return max(engagement_score - age_hours * 5, 0)


def upsert_trend(db: Session, item: NormalizedDouyinVideo) -> DouyinTrend:
    trend = db.query(DouyinTrend).filter(DouyinTrend.source_url == item.source_url).first()
    if not trend and item.video_id:
        trend = db.query(DouyinTrend).filter(DouyinTrend.video_id == item.video_id).first()
    if not trend:
        trend = DouyinTrend(source_url=item.source_url)
        db.add(trend)

    trend.video_id = item.video_id
    trend.source_url = item.source_url
    trend.author_name = item.author_name
    trend.author_id = item.author_id
    trend.caption = item.caption
    trend.cover_url = item.cover_url
    trend.like_count = item.like_count
    trend.comment_count = item.comment_count
    trend.share_count = item.share_count
    trend.collect_count = item.collect_count
    trend.duration = item.duration
    trend.create_time = item.create_time
    trend.hot_score = calculate_hot_score(
        item.like_count,
        item.comment_count,
        item.share_count,
        item.collect_count,
        item.create_time,
    )
    trend.niche = item.niche
    if trend.status in {"failed", "done"}:
        trend.status = "found"
    trend.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(trend)
    return trend


def attach_local_file_to_trend(db: Session, trend: DouyinTrend, file_path: Path) -> DouyinTrend:
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"File not found: {file_path}")
    if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video extension: {file_path.suffix}")

    settings = get_settings()
    raw_dir = settings.storage_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    destination = raw_dir / f"trend_{trend.id}_{safe_file_name(file_path.name)}"
    if file_path.resolve() != destination.resolve():
        shutil.copy2(file_path, destination)

    trend.raw_video_path = str(destination.resolve())
    trend.imported_file_name = file_path.name
    trend.status = "downloaded"
    trend.waiting_download = False
    trend.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(trend)
    return trend


def find_waiting_trend(db: Session, window_minutes: int) -> DouyinTrend | None:
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    return (
        db.query(DouyinTrend)
        .filter(DouyinTrend.waiting_download.is_(True))
        .filter(DouyinTrend.status == "waiting_download")
        .filter(DouyinTrend.waiting_since >= cutoff)
        .order_by(DouyinTrend.waiting_since.desc())
        .first()
    )


def safe_file_name(name: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in name)


def enqueue_video_processing_for_trend(trend_id: int) -> str:
    return f"Video imported and ready for processing. trend_id={trend_id}"
