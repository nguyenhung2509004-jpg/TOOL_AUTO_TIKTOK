from pathlib import Path

from app.models.video import RenderJob, SourceVideo, VideoSegment


def cleanup_intermediate_files(video: SourceVideo, segments: list[VideoSegment], jobs: list[RenderJob]) -> tuple[int, int]:
    keep = {Path(job.output_video_path).resolve() for job in jobs if job.output_video_path}
    keep.update(Path(job.subtitle_path).resolve() for job in jobs if job.subtitle_path)
    candidates: list[Path] = []
    if video.original_audio_path:
        candidates.append(Path(video.original_audio_path))
    candidates.extend(Path(segment.voice_segment_path) for segment in segments if segment.voice_segment_path)

    deleted = 0
    kept = 0
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved in keep:
                kept += 1
                continue
            if resolved.exists() and resolved.is_file():
                resolved.unlink()
                deleted += 1
        except OSError:
            kept += 1
    return deleted, kept
