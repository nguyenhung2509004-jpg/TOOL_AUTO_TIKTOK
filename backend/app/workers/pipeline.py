from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.video import RenderJob, SourceVideo, VideoSegment
from app.schemas.video import RenderRequest
from app.services.asr import ASRService
from app.services.downloader import DouyinDownloader
from app.services.media import build_srt, extract_audio, ffprobe_duration, render_video
from app.services.translator import TranslationService
from app.services.tts import TTSService


def new_task_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


async def import_video_job(video_id: int) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        video = db.get(SourceVideo, video_id)
        if not video:
            return
        video.status = "downloading"
        db.commit()

        downloader = DouyinDownloader(settings.storage_dir, settings.douyin_cookies_path)
        raw_path, meta = await downloader.download(video.id, video.source_url)
        video.caption_original = meta.get("resolved_url")
        if not raw_path:
            video.status = "failed"
            video.error_message = meta.get("warning") or "Unable to download raw Douyin video."
            video.raw_video_path = None
            video.original_audio_path = None
            video.duration = None
            db.query(VideoSegment).filter(VideoSegment.video_id == video.id).delete()
            db.commit()
            return

        video.raw_video_path = str(raw_path)
        video.duration = ffprobe_duration(raw_path)
        audio_path = extract_audio(raw_path, settings.storage_dir / "audio" / f"{video.id}.mp3")
        if not audio_path:
            video.status = "failed"
            video.error_message = "Raw video downloaded, but FFmpeg could not extract audio."
            db.commit()
            return
        video.original_audio_path = str(audio_path)

        video.status = "transcribing"
        db.commit()

        db.query(VideoSegment).filter(VideoSegment.video_id == video.id).delete()
        db.commit()

        transcript = ASRService().transcribe(Path(video.original_audio_path) if video.original_audio_path else None)
        if not transcript:
            raise RuntimeError("ASR returned no transcript segments.")
        for order, item in enumerate(transcript, start=1):
            db.add(
                VideoSegment(
                    video_id=video.id,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    text_cn=item.text_cn,
                    display_order=order,
                )
            )
        db.commit()

        segments = _segments(db, video.id)
        if not segments:
            raise RuntimeError("No transcript segments were stored.")
        translator = TranslationService()
        for segment_id, text_vi, optimized in translator.translate_segments(segments):
            segment = db.get(VideoSegment, segment_id)
            segment.text_vi = text_vi
            segment.text_vi_optimized = optimized

        video.status = "ready"
        db.commit()
    except Exception as exc:
        _fail_video(db, video_id, exc)
    finally:
        db.close()


def import_local_video_job(video_id: int) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        video = db.get(SourceVideo, video_id)
        if not video:
            return
        if not video.raw_video_path:
            raise RuntimeError("Local video record has no raw_video_path.")

        raw_path = Path(video.raw_video_path)
        if not raw_path.exists() or not raw_path.is_file():
            raise RuntimeError(f"Local video file not found: {raw_path}")

        video.status = "extracting_audio"
        video.error_message = None
        video.duration = ffprobe_duration(raw_path)
        db.query(VideoSegment).filter(VideoSegment.video_id == video.id).delete()
        db.commit()

        audio_path = extract_audio(raw_path, settings.storage_dir / "audio" / f"{video.id}.mp3")
        if not audio_path:
            raise RuntimeError("FFmpeg could not extract audio from local video.")
        video.original_audio_path = str(audio_path)
        video.status = "transcribing"
        db.commit()

        transcript = ASRService().transcribe(audio_path)
        if not transcript:
            raise RuntimeError("ASR returned no transcript segments.")

        for order, item in enumerate(transcript, start=1):
            db.add(
                VideoSegment(
                    video_id=video.id,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    text_cn=item.text_cn,
                    display_order=order,
                )
            )
        db.commit()

        segments = _segments(db, video.id)
        translator = TranslationService()
        for segment_id, text_vi, optimized in translator.translate_segments(segments):
            segment = db.get(VideoSegment, segment_id)
            segment.text_vi = text_vi
            segment.text_vi_optimized = optimized

        video.status = "ready"
        db.commit()
    except Exception as exc:
        _fail_video(db, video_id, exc)
    finally:
        db.close()


def render_job(job_id: int, request: RenderRequest) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(RenderJob, job_id)
        if not job:
            return
        video = db.get(SourceVideo, job.video_id)
        job.status = "rendering"
        job.progress_percentage = 10
        db.commit()

        if not video or not video.raw_video_path or not Path(video.raw_video_path).exists():
            raise RuntimeError("No raw video found. Import a real downloadable video before rendering.")

        segments = _segments(db, job.video_id)
        if not segments:
            raise RuntimeError("No real transcript segments found. Run ASR/import successfully before rendering.")
        tts = TTSService(settings.storage_dir)
        voice_paths: list[tuple[Path, float]] = []
        for segment in segments:
            text = segment.text_vi_optimized or segment.text_vi or segment.text_cn
            target = segment.end_time - segment.start_time
            voice_path, voice_duration, speed_ratio = tts.synthesize(segment.id, text, target)
            segment.voice_segment_path = str(voice_path) if voice_path else None
            segment.voice_duration = voice_duration
            segment.speed_ratio = speed_ratio
            if voice_path:
                voice_paths.append((voice_path, segment.start_time))
        if not voice_paths:
            raise RuntimeError("No real TTS voice files were generated.")
        job.progress_percentage = 45
        db.commit()

        subtitle_path = build_srt(segments, settings.storage_dir / "subtitles" / f"{video.id}.srt")
        job.subtitle_path = str(subtitle_path)
        job.progress_percentage = 60
        db.commit()

        output_path = settings.storage_dir / "renders" / f"{video.id}_{job.id}.mp4"
        render_video(
            Path(video.raw_video_path),
            voice_paths,
            subtitle_path,
            output_path,
            request.original_audio_volume,
            request.burn_subtitles,
        )
        job.output_video_path = str(output_path)

        job.status = "completed"
        job.progress_percentage = 100
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        job = db.get(RenderJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _segments(db: Session, video_id: int) -> list[VideoSegment]:
    return (
        db.query(VideoSegment)
        .filter(VideoSegment.video_id == video_id)
        .order_by(VideoSegment.display_order.asc())
        .all()
    )


def _fail_video(db: Session, video_id: int, exc: Exception) -> None:
    video = db.get(SourceVideo, video_id)
    if video:
        video.status = "failed"
        video.error_message = str(exc)
        db.commit()
