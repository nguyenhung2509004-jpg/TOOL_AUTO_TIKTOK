from app.models.video import SourceVideo, VideoSegment


DEFAULT_HASHTAGS = ["#vietdub", "#douyin", "#tiktokvn", "#review"]


def build_caption(video: SourceVideo, segments: list[VideoSegment]) -> tuple[str, list[str]]:
    first_line = next(
        (segment.text_vi_optimized or segment.text_vi for segment in segments if segment.text_vi_optimized or segment.text_vi),
        "Video dub tieng Viet",
    )
    source_note = f"Nguon: {video.caption_original}" if video.caption_original else "Auto Viet dub"
    caption = f"{first_line}\n{source_note}\n{' '.join(DEFAULT_HASHTAGS)}"
    return caption, DEFAULT_HASHTAGS
