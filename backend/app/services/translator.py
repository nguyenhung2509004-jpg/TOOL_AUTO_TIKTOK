from app.models.video import VideoSegment


class TranslationService:
    WORDS_PER_SECOND = 2.5

    def translate_segments(self, segments: list[VideoSegment]) -> list[tuple[int, str, str]]:
        raise RuntimeError(
            "Real translation provider is not configured. Configure OpenAI/Gemini before auto-translation."
        )

    def warning_for(self, text: str | None, max_duration: float) -> bool:
        if not text:
            return False
        return len(text.split()) > int(max_duration * self.WORDS_PER_SECOND)
