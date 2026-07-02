from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import get_settings


@dataclass
class TranscriptSegment:
    start_time: float
    end_time: float
    text_cn: str


class ASRService:
    def transcribe(self, audio_path: Path | None) -> list[TranscriptSegment]:
        if not audio_path or not audio_path.exists():
            raise RuntimeError("No extracted audio found for ASR.")

        settings = get_settings()
        if settings.asr_provider.lower() == "openai":
            return self._transcribe_openai(audio_path)
        return self._transcribe_local(audio_path)

    def _transcribe_openai(self, audio_path: Path) -> list[TranscriptSegment]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured for automatic ASR.")
        with audio_path.open("rb") as audio_file:
            response = httpx.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                data={
                    "model": settings.openai_asr_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                files={"file": (audio_path.name, audio_file, "audio/mpeg")},
                timeout=600,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI ASR failed: {response.text[:500]}")

        payload = response.json()
        return self._segments_from_openai_payload(payload)

    def _transcribe_local(self, audio_path: Path) -> list[TranscriptSegment]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Local ASR is not installed. Rebuild backend after installing faster-whisper."
            ) from exc

        settings = get_settings()
        model_dir = settings.storage_dir / "models" / "faster-whisper"
        model_dir.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            settings.local_whisper_model,
            device="cpu",
            compute_type="int8",
            download_root=str(model_dir),
        )
        attempts = [
            {"language": "zh", "vad_filter": True},
            {"language": "zh", "vad_filter": False},
            {"language": None, "vad_filter": True},
            {"language": None, "vad_filter": False},
        ]
        for options in attempts:
            raw_segments, _info = model.transcribe(
                str(audio_path),
                language=options["language"],
                vad_filter=options["vad_filter"],
                beam_size=5,
                condition_on_previous_text=False,
            )
            segments = self._segments_from_local_items(raw_segments)
            if segments:
                return segments

        if settings.openai_api_key:
            try:
                return self._transcribe_openai(audio_path)
            except Exception as exc:
                raise RuntimeError(
                    "Both local faster-whisper and OpenAI ASR returned no usable transcript. "
                    f"OpenAI fallback error: {exc}"
                ) from exc
        raise RuntimeError("Local faster-whisper ASR returned no transcript text.")

    def _segments_from_local_items(self, items) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                start_time=float(item.start),
                end_time=max(float(item.end), float(item.start) + 0.5),
                text_cn=item.text.strip(),
            )
            for item in items
            if item.text.strip()
        ]

    def _segments_from_openai_payload(self, payload: dict) -> list[TranscriptSegment]:
        segments = [
            TranscriptSegment(
                start_time=float(item.get("start", 0)),
                end_time=max(float(item.get("end", 0)), float(item.get("start", 0)) + 0.5),
                text_cn=(item.get("text") or "").strip(),
            )
            for item in payload.get("segments", [])
            if (item.get("text") or "").strip()
        ]
        if segments:
            return segments

        text = (payload.get("text") or "").strip()
        if text:
            return [TranscriptSegment(start_time=0, end_time=30, text_cn=text)]
        raise RuntimeError("OpenAI ASR returned no transcript text.")
