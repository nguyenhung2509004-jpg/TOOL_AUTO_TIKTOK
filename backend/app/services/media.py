import subprocess
from pathlib import Path

from app.core.config import get_settings


def ffprobe_duration(path: Path) -> float | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


def extract_audio(video_path: Path, output_path: Path) -> Path | None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "mp3", str(output_path)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        return output_path
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def build_srt(segments: list, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.text_vi_optimized or segment.text_vi or segment.text_cn
        lines.extend(
            [
                str(index),
                f"{_srt_time(segment.start_time)} --> {_srt_time(segment.end_time)}",
                text,
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def render_video(
    input_video: Path,
    voice_paths: list[tuple[Path, float, float, float]],
    subtitle_path: Path,
    output_path: Path,
    original_audio_volume: float,
    voice_volume: float,
    burn_subtitles: bool,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not voice_paths:
        video_filter = []
        if burn_subtitles:
            escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
            video_filter = ["-vf", f"subtitles='{escaped}'"]

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            *video_filter,
            "-c:v",
            "libx264" if burn_subtitles else "copy",
            "-c:a",
            "aac",
            "-af",
            f"volume={original_audio_volume}",
            str(output_path),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    inputs = ["-i", str(input_video)]
    filter_parts = [f"[0:a]volume={original_audio_volume}[bg]"]
    mix_inputs = ["[bg]"]
    settings = get_settings()
    pause_seconds = max(float(settings.voice_segment_pause_seconds), 0)
    max_tempo = max(float(settings.voice_max_tempo), 1.0)
    fit_mode = settings.voice_fit_mode.strip().lower()
    preserve_natural_timing = fit_mode in {"natural", "preserve", "original"}
    trim_to_slot = fit_mode in {"strict", "trim", "cut"}
    next_available_start = 0.0

    for idx, (voice_path, start_time, end_time, voice_duration) in enumerate(voice_paths, start=1):
        inputs.extend(["-i", str(voice_path)])
        label = f"aud{idx}"
        slot_duration = max(end_time - start_time - pause_seconds, 0.25)
        scheduled_start = start_time
        tempo = 1.0
        effective_limit = voice_duration if voice_duration else slot_duration

        if preserve_natural_timing:
            scheduled_start = max(start_time, next_available_start)
        elif voice_duration and voice_duration > slot_duration:
            tempo = min(max(voice_duration / slot_duration, 1.0), max_tempo)
            if trim_to_slot:
                effective_limit = min(slot_duration, voice_duration / tempo)
            else:
                effective_limit = voice_duration / tempo

        if preserve_natural_timing:
            next_available_start = scheduled_start + effective_limit + pause_seconds

        delay_ms = int(scheduled_start * 1000)
        audio_filters = [
            f"volume={voice_volume}",
            *_atempo_filters(tempo),
            *([f"atrim=0:{effective_limit:.3f}"] if trim_to_slot else []),
            "asetpts=PTS-STARTPTS",
            f"adelay={delay_ms}|{delay_ms}",
        ]
        filter_parts.append(f"[{idx}:a]{','.join(audio_filters)}[{label}]")
        mix_inputs.append(f"[{label}]")

    filter_parts.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first[aout]")
    video_filter = []
    if burn_subtitles:
        escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
        video_filter = ["-vf", f"subtitles='{escaped}'"]

    command = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        *video_filter,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "libx264" if burn_subtitles else "copy",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
    return output_path


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _atempo_filters(tempo: float) -> list[str]:
    if tempo <= 1.001:
        return []
    parts: list[str] = []
    remaining = tempo
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    parts.append(f"atempo={remaining:.3f}")
    return parts
