import subprocess
from pathlib import Path


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
    voice_paths: list[tuple[Path, float]],
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

    for idx, (voice_path, start_time) in enumerate(voice_paths, start=1):
        inputs.extend(["-i", str(voice_path)])
        delay_ms = int(start_time * 1000)
        label = f"aud{idx}"
        filter_parts.append(f"[{idx}:a]volume={voice_volume},adelay={delay_ms}|{delay_ms}[{label}]")
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
