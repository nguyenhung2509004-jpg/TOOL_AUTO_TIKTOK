from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start_time: float
    end_time: float
    text_cn: str


class ASRService:
    def transcribe(self, audio_path: Path | None) -> list[TranscriptSegment]:
        if not audio_path or not audio_path.exists():
            raise RuntimeError("No extracted audio found for ASR.")
        raise RuntimeError(
            "Real ASR provider is not configured. Configure Whisper/faster-whisper before transcription."
        )
