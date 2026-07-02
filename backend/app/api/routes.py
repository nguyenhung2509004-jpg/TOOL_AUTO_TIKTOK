import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.video import RenderJob, SourceVideo, VideoSegment
from app.schemas.video import (
    CaptionOut,
    CleanupOut,
    DeleteVideoResponse,
    DeleteRenderJobResponse,
    ImportRequest,
    ImportResponse,
    LocalScanResponse,
    RenderJobOut,
    RenderRequest,
    SegmentOut,
    SegmentUpdateRequest,
    SourceVideoOut,
    TTSVoiceOut,
    VideoUpdateRequest,
)
from app.services.cleanup import cleanup_intermediate_files
from app.services.export import build_caption
from app.services.translator import TranslationService
from app.workers.pipeline import import_local_video_job, import_video_job, new_task_id, render_job

router = APIRouter(prefix="/api")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def _configured_tts_voices() -> list[TTSVoiceOut]:
    settings = get_settings()
    voices = [
        TTSVoiceOut(id="fpt_banmai", label="FPT - Ban Mai", provider="fpt_ai", voice_id="banmai"),
        TTSVoiceOut(id="fpt_leminh", label="FPT - Le Minh", provider="fpt_ai", voice_id="leminh"),
    ]
    for index, raw_item in enumerate(settings.omnivoice_voices.split(";"), start=1):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 4:
            label, voice_id, ref_audio, ref_text = parts[0], parts[1], parts[2], "|".join(parts[3:])
        elif len(parts) >= 3:
            label, ref_audio, ref_text = parts[0], parts[1], "|".join(parts[2:])
            voice_id = f"voice_{index}"
        else:
            continue
        if not voice_id or not ref_audio or not ref_text:
            continue
        voices.append(
            TTSVoiceOut(
                id=f"omnivoice_{voice_id}",
                label=label.strip() or f"OmniVoice {index}",
                provider="omnivoice",
                voice_id=voice_id,
            )
        )
    return voices


@router.post("/douyin/import", response_model=ImportResponse, status_code=202)
async def import_douyin(payload: ImportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    video = SourceVideo(source_url=payload.url, status="pending")
    db.add(video)
    db.commit()
    db.refresh(video)

    task_id = new_task_id("job_dw")
    background_tasks.add_task(import_video_job, video.id)
    return ImportResponse(
        video_id=video.id,
        status="downloading",
        task_id=task_id,
        message="Dang phan tich link va tai video tu Douyin...",
    )


@router.get("/tts/voices", response_model=list[TTSVoiceOut])
def list_tts_voices():
    return _configured_tts_voices()


@router.post("/local/scan", response_model=LocalScanResponse, status_code=202)
def scan_local_inbox(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    settings = get_settings()
    settings.watch_dir.mkdir(parents=True, exist_ok=True)

    imported: list[ImportResponse] = []
    skipped: list[str] = []
    files = sorted(
        path for path in settings.watch_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )

    for path in files:
        raw_path = str(path.resolve())
        existing = db.query(SourceVideo).filter(SourceVideo.raw_video_path == raw_path).first()
        if existing:
            skipped.append(path.name)
            continue

        video = SourceVideo(
            platform="local",
            source_url=f"file://{raw_path}",
            caption_original=path.stem,
            raw_video_path=raw_path,
            status="pending",
        )
        db.add(video)
        db.commit()
        db.refresh(video)

        task_id = new_task_id("job_local")
        background_tasks.add_task(import_local_video_job, video.id)
        imported.append(
            ImportResponse(
                video_id=video.id,
                status="extracting_audio",
                task_id=task_id,
                message=f"Queued local video: {path.name}",
            )
        )

    return LocalScanResponse(imported=imported, skipped=skipped, watch_dir=str(settings.watch_dir))


@router.post("/local/upload", response_model=ImportResponse, status_code=202)
def upload_local_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported video file type: {suffix or 'unknown'}")

    settings = get_settings()
    upload_dir = settings.storage_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(file.filename or "video").stem.replace(" ", "_")[:80] or "video"
    target = upload_dir / f"{uuid4().hex[:12]}_{safe_stem}{suffix}"

    try:
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    finally:
        file.file.close()

    raw_path = str(target.resolve())
    video = SourceVideo(
        platform="local",
        source_url=f"file://{raw_path}",
        caption_original=Path(file.filename or target.name).stem,
        raw_video_path=raw_path,
        status="pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    task_id = new_task_id("job_upload")
    background_tasks.add_task(import_local_video_job, video.id)
    return ImportResponse(
        video_id=video.id,
        status="extracting_audio",
        task_id=task_id,
        message=f"Queued uploaded video: {file.filename or target.name}",
    )


@router.post("/videos/{video_id}/reimport", response_model=ImportResponse, status_code=202)
async def reimport_video(video_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.status = "pending"
    video.error_message = None
    db.commit()

    task_id = new_task_id("job_retry")
    is_local_video = video.platform == "local" or video.source_url.startswith("file://") or bool(video.raw_video_path)
    if is_local_video:
        if not video.raw_video_path:
            raise HTTPException(status_code=400, detail="Local video has no raw_video_path to reprocess.")
        background_tasks.add_task(import_local_video_job, video.id)
        return ImportResponse(
            video_id=video.id,
            status="extracting_audio",
            task_id=task_id,
            message="Dang xu ly lai file video local...",
        )

    background_tasks.add_task(import_video_job, video.id)
    return ImportResponse(
        video_id=video.id,
        status="downloading",
        task_id=task_id,
        message="Dang tai lai video voi cau hinh downloader moi...",
    )


@router.get("/videos", response_model=list[SourceVideoOut])
def list_videos(db: Session = Depends(get_db)):
    return db.query(SourceVideo).order_by(SourceVideo.created_at.desc()).limit(50).all()


@router.get("/videos/{video_id}", response_model=SourceVideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.put("/videos/{video_id}", response_model=SourceVideoOut)
def update_video(video_id: int, payload: VideoUpdateRequest, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if payload.source_url is not None:
        source_url = payload.source_url.strip()
        if not source_url:
            raise HTTPException(status_code=400, detail="source_url cannot be empty")
        video.source_url = source_url
    if payload.caption_original is not None:
        video.caption_original = payload.caption_original.strip() or None
    db.commit()
    db.refresh(video)
    return video


@router.delete("/videos/{video_id}", response_model=DeleteVideoResponse)
def delete_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    segments = db.query(VideoSegment).filter(VideoSegment.video_id == video_id).all()
    jobs = db.query(RenderJob).filter(RenderJob.video_id == video_id).all()
    deleted_files, _kept_files = cleanup_intermediate_files(video, segments, jobs)
    db.delete(video)
    db.commit()
    return DeleteVideoResponse(video_id=video_id, deleted_files=deleted_files, message="Video deleted")


@router.get("/videos/{video_id}/raw")
def preview_raw_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video or not video.raw_video_path:
        raise HTTPException(status_code=404, detail="Raw video not found")
    path = Path(video.raw_video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Raw video file missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/videos/{video_id}/segments", response_model=list[SegmentOut])
def get_segments(video_id: int, db: Session = Depends(get_db)):
    segments = (
        db.query(VideoSegment)
        .filter(VideoSegment.video_id == video_id)
        .order_by(VideoSegment.display_order.asc())
        .all()
    )
    translator = TranslationService()
    return [
        SegmentOut(
            id=segment.id,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text_cn=segment.text_cn,
            text_vi=segment.text_vi,
            text_vi_optimized=segment.text_vi_optimized,
            voice_duration=segment.voice_duration,
            max_duration=segment.end_time - segment.start_time,
            warning=translator.warning_for(segment.text_vi_optimized or segment.text_vi, segment.end_time - segment.start_time),
        )
        for segment in segments
    ]


@router.put("/videos/{video_id}/segments", response_model=list[SegmentOut])
def update_segments(video_id: int, payload: SegmentUpdateRequest, db: Session = Depends(get_db)):
    known = {
        segment.id: segment
        for segment in db.query(VideoSegment).filter(VideoSegment.video_id == video_id).all()
    }
    for item in payload.segments:
        segment = known.get(item.id)
        if segment:
            segment.text_vi = item.text_vi
            segment.text_vi_optimized = item.text_vi_optimized
    db.commit()
    return get_segments(video_id, db)


@router.post("/videos/{video_id}/render", response_model=RenderJobOut, status_code=202)
def render(video_id: int, payload: RenderRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job = RenderJob(
        video_id=video_id,
        tts_provider=payload.tts_provider,
        voice_id=payload.voice_id,
        original_audio_volume=payload.original_audio_volume,
        voice_volume=payload.voice_volume,
        burn_subtitles=payload.burn_subtitles,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(render_job, job.id, payload)
    return job


@router.get("/render-jobs", response_model=list[RenderJobOut])
def list_render_jobs(video_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(RenderJob)
    if video_id is not None:
        query = query.filter(RenderJob.video_id == video_id)
    return query.order_by(RenderJob.created_at.desc()).limit(100).all()


@router.get("/render-jobs/{job_id}", response_model=RenderJobOut)
def get_render_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RenderJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    return job


@router.post("/render-jobs/{job_id}/cancel", response_model=DeleteRenderJobResponse)
def cancel_render_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RenderJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Render job not found")
    db.delete(job)
    db.commit()
    return DeleteRenderJobResponse(job_id=job_id, deleted=True, message="Render job deleted")


@router.get("/render-jobs/{job_id}/download")
def download_render(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RenderJob, job_id)
    if not job or not job.output_video_path:
        raise HTTPException(status_code=404, detail="Rendered video not found")
    path = Path(job.output_video_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rendered file missing")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/videos/{video_id}/caption", response_model=CaptionOut)
def get_caption(video_id: int, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    segments = (
        db.query(VideoSegment)
        .filter(VideoSegment.video_id == video_id)
        .order_by(VideoSegment.display_order.asc())
        .all()
    )
    caption, hashtags = build_caption(video, segments)
    return CaptionOut(caption=caption, hashtags=hashtags)


@router.post("/videos/{video_id}/cleanup", response_model=CleanupOut)
def cleanup_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(SourceVideo, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    segments = db.query(VideoSegment).filter(VideoSegment.video_id == video_id).all()
    jobs = db.query(RenderJob).filter(RenderJob.video_id == video_id).all()
    deleted, kept = cleanup_intermediate_files(video, segments, jobs)
    return CleanupOut(video_id=video_id, deleted_files=deleted, kept_files=kept)
