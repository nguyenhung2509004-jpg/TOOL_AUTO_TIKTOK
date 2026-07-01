from pathlib import Path


class TTSService:
    def __init__(self, storage_dir: Path):
        self.segment_dir = storage_dir / "segments"
        self.segment_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, segment_id: int, text: str, target_duration: float) -> tuple[Path | None, float, float]:
        raise RuntimeError(
            "Real TTS provider is not configured. Configure ElevenLabs/FPT before rendering dubbed audio."
        )
