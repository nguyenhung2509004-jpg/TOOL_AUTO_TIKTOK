import json
import re

import httpx

from app.core.config import get_settings
from app.models.video import VideoSegment


class TranslationService:
    WORDS_PER_SECOND = 2.5

    def translate_segments(self, segments: list[VideoSegment]) -> list[tuple[int, str, str]]:
        if not segments:
            return []
        settings = get_settings()
        if settings.openai_api_key:
            try:
                return self._translate_openai(segments)
            except Exception:
                return self._translate_google(segments)
        return self._translate_google(segments)

    def _translate_openai(self, segments: list[VideoSegment]) -> list[tuple[int, str, str]]:
        settings = get_settings()
        payload = self._segment_payload(segments)
        video_context = self._build_video_context(payload)
        translated: dict[int, tuple[str, str]] = {}
        batch_size = max(settings.translation_batch_size, 1)
        for start in range(0, len(payload), batch_size):
            batch = payload[start:start + batch_size]
            previous_items = payload[max(0, start - 3):start]
            next_items = payload[start + batch_size:start + batch_size + 3]
            translated.update(
                self._translate_openai_batch(
                    batch=batch,
                    previous_items=previous_items,
                    next_items=next_items,
                    video_context=video_context,
                    glossary=settings.translation_glossary,
                )
            )
        return [
            (segment.id, translated.get(segment.id, ("", ""))[0], translated.get(segment.id, ("", ""))[1])
            for segment in segments
        ]

    def _segment_payload(self, segments: list[VideoSegment]) -> list[dict]:
        return [
            {
                "id": segment.id,
                "start": segment.start_time,
                "end": segment.end_time,
                "duration": round(max(segment.end_time - segment.start_time, 0), 2),
                "text_cn": segment.text_cn,
            }
            for segment in segments
        ]

    def _build_video_context(self, payload: list[dict]) -> str:
        settings = get_settings()
        transcript = "\n".join(
            f'{index + 1}. [{self._format_time(item["start"])}-{self._format_time(item["end"])}] {item["text_cn"]}'
            for index, item in enumerate(payload[:120])
        )
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_translation_model,
                "temperature": 0.15,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Bạn là biên tập viên nội dung Douyin. Hãy đọc transcript và tạo ngữ cảnh ngắn "
                            "để người dịch tiếng Việt hiểu đúng mạch video. Không dịch từng segment ở bước này."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Tạo video_context gồm: chủ đề, mục đích video, người nói/đối tượng, giọng điệu, "
                            "các thuật ngữ cần thống nhất, và mạch ý chính theo thứ tự.\n\nTranscript:\n"
                            f"{transcript}"
                        ),
                    },
                ],
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI context summary failed: {response.text[:500]}")
        return response.json()["choices"][0]["message"]["content"].strip()

    def _translate_openai_batch(
        self,
        batch: list[dict],
        previous_items: list[dict],
        next_items: list[dict],
        video_context: str,
        glossary: str,
    ) -> dict[int, tuple[str, str]]:
        settings = get_settings()
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_translation_model,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Bạn là biên tập viên lồng tiếng Việt cho video ngắn Douyin. "
                            "Không dịch máy từng chữ. Hãy dịch theo ngữ cảnh toàn video.\n\n"
                            "Yêu cầu:\n"
                            "- Giữ đúng ý gốc.\n"
                            "- Văn phong tự nhiên, dễ nghe khi lồng tiếng.\n"
                            "- Các câu phải liên kết với nhau.\n"
                            "- Thống nhất cách gọi nhân vật, sản phẩm, thuật ngữ.\n"
                            "- Nếu tiếng Trung dùng ẩn ý, hãy diễn đạt rõ bằng tiếng Việt.\n"
                            "- Không thêm thông tin sai.\n"
                            "- Độ dài mỗi segment phải phù hợp thời lượng nói.\n\n"
                            "Trả về JSON duy nhất có key segments, là array object: "
                            '{"id": number, "text_vi": string, "text_vi_optimized": string}.'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "video_context": video_context,
                                "glossary": glossary,
                                "previous_context_segments": previous_items,
                                "segments_to_translate": batch,
                                "next_context_segments": next_items,
                                "instruction": (
                                    "Dịch segments_to_translate sang tiếng Việt. text_vi giữ sát nghĩa, "
                                    "text_vi_optimized là bản lồng tiếng tự nhiên hơn nhưng không sai ý. "
                                    "Dùng previous/next chỉ để hiểu mạch, không trả về chúng."
                                ),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            timeout=180,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI translation failed: {response.text[:500]}")
        content = response.json()["choices"][0]["message"]["content"]
        data = self._loads_json_object(content)
        return {
            int(item["id"]): (
                str(item.get("text_vi") or "").strip(),
                str(item.get("text_vi_optimized") or item.get("text_vi") or "").strip(),
            )
            for item in data.get("segments", [])
            if item.get("id") is not None
        }

    def _loads_json_object(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _translate_google(self, segments: list[VideoSegment]) -> list[tuple[int, str, str]]:
        translated: list[tuple[int, str, str]] = []
        with httpx.Client(timeout=60) as client:
            for segment in segments:
                text = segment.text_cn.strip()
                if not text:
                    translated.append((segment.id, "", ""))
                    continue
                response = client.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params={
                        "client": "gtx",
                        "sl": "zh-CN",
                        "tl": "vi",
                        "dt": "t",
                        "q": text,
                    },
                )
                if response.status_code >= 400:
                    raise RuntimeError(f"Google translation failed: {response.text[:300]}")
                data = response.json()
                text_vi = "".join(part[0] for part in data[0] if part and part[0]).strip()
                translated.append((segment.id, text_vi, text_vi))
        return translated

    def warning_for(self, text: str | None, max_duration: float) -> bool:
        if not text:
            return False
        return len(text.split()) > int(max_duration * self.WORDS_PER_SECOND)

    def _format_time(self, value: float) -> str:
        minutes = int(value // 60)
        seconds = int(value % 60)
        return f"{minutes:02d}:{seconds:02d}"
