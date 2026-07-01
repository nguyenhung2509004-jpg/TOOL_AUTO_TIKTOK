from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings


class DouyinProviderError(RuntimeError):
    pass


@dataclass
class NormalizedDouyinVideo:
    video_id: str | None
    source_url: str
    author_name: str | None
    author_id: str | None
    caption: str | None
    cover_url: str | None
    like_count: int
    comment_count: int
    share_count: int
    collect_count: int
    duration: float | None
    create_time: int | None
    niche: str


CATEGORY_SEARCH_TERMS = {
    "\u751f\u6d3b\u6280\u5de7": ["\u751f\u6d3b\u6280\u5de7", "\u751f\u6d3b\u5c0f\u5999\u62db", "\u5bb6\u5c45\u5999\u62db", "\u6536\u7eb3", "\u6e05\u6d01\u6280\u5de7"],
    "\u7f8e\u98df": ["\u7f8e\u98df", "\u5bb6\u5e38\u83dc", "\u505a\u996d", "\u63a2\u5e97", "\u5c0f\u5403", "\u98df\u8c31"],
    "\u5ba0\u7269": ["\u5ba0\u7269", "\u732b", "\u72d7", "\u840c\u5ba0", "\u517b\u5ba0", "\u5ba0\u7269\u65e5\u5e38"],
    "\u79d1\u6280": ["\u79d1\u6280", "\u6570\u7801", "\u624b\u673a", "AI", "\u7535\u8111", "\u667a\u80fd\u8bbe\u5907"],
    "\u6d4b\u8bc4": ["\u6d4b\u8bc4", "\u5f00\u7bb1", "\u8bd5\u7528", "\u597d\u7269", "\u4ea7\u54c1\u6d4b\u8bc4", "\u8bc4\u6d4b"],
    "\u641e\u7b11": ["\u641e\u7b11", "\u6bb5\u5b50", "\u7206\u7b11", "\u5e7d\u9ed8", "\u6574\u6d3b", "\u540d\u573a\u9762"],
    "\u5b66\u4e60": ["\u5b66\u4e60", "\u77e5\u8bc6", "\u6559\u7a0b", "\u82f1\u8bed", "\u8003\u8bd5", "\u8bfb\u4e66"],
    "\u7f8e\u5986": ["\u7f8e\u5986", "\u5316\u5986", "\u62a4\u80a4", "\u53d8\u7f8e", "\u53e3\u7ea2", "\u7a7f\u642d"],
    "\u65c5\u884c": ["\u65c5\u884c", "\u65c5\u6e38", "\u653b\u7565", "\u666f\u70b9", "\u81ea\u9a7e", "\u9732\u8425"],
    "\u6bcd\u5a74": ["\u6bcd\u5a74", "\u80b2\u513f", "\u5b9d\u5b9d", "\u5b55\u5987", "\u65e9\u6559", "\u513f\u7ae5"],
    "\u8fd0\u52a8": ["\u8fd0\u52a8", "\u5065\u8eab", "\u7bee\u7403", "\u8db3\u7403", "\u8dd1\u6b65", "\u745c\u4f3d"],
    "\u6c7d\u8f66": ["\u6c7d\u8f66", "\u65b0\u8f66", "\u8bd5\u9a7e", "\u4e8c\u624b\u8f66", "\u7528\u8f66", "\u7535\u52a8\u8f66"],
}


class TikHubClient:
    billboard_video_path = "/api/v1/douyin/billboard/fetch_hot_total_video_list"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.tikhub_api_key
        self.base_url = settings.tikhub_base_url.rstrip("/")
        self.hot_search_path = settings.tikhub_hot_search_path

    async def search_hot_videos(self, niche: str, limit: int = 20) -> list[NormalizedDouyinVideo]:
        if not self.api_key:
            raise DouyinProviderError("TIKHUB_API_KEY is not configured.")

        url = f"{self.base_url}{self.billboard_video_path}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "page": 1,
            "page_size": max(limit, 10),
            "date_window": 1,
            "sub_type": "1001",
            "keyword": niche,
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise DouyinProviderError("TikHub provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise DouyinProviderError(f"TikHub provider request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise DouyinProviderError("TikHub provider rejected the API key.")
        if response.status_code >= 400:
            raise DouyinProviderError(f"TikHub provider returned HTTP {response.status_code}.")

        response.encoding = "utf-8"
        try:
            payload = response.json()
        except ValueError as exc:
            raise DouyinProviderError("TikHub provider returned invalid JSON.") from exc

        self._raise_for_tikhub_business_error(payload)
        items = self._extract_items(payload)
        if not items:
            raise DouyinProviderError("TikHub billboard endpoint returned no videos for this category.")
        normalized_items = [self._normalize_item(item, niche) for item in items]
        return self._filter_by_niche(normalized_items, niche)[:limit]

    def _raise_for_tikhub_business_error(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        detail = payload.get("detail")
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("message_zh") or "TikHub provider rejected the request."
            raise DouyinProviderError(str(message))

        data = payload.get("data")
        if isinstance(data, dict) and data.get("code") not in (None, 0, 200):
            message = data.get("message") or "TikHub provider returned a business error."
            raise DouyinProviderError(str(message))

    def _extract_items(self, payload: Any) -> list[dict[str, Any]] | None:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return None

        candidates = self._collect_list_candidates(payload)
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return None

    def _collect_list_candidates(self, payload: dict[str, Any]) -> list[Any]:
        direct_keys = [
            "aweme_list",
            "item_list",
            "items",
            "videos",
            "list",
            "word_list",
            "trending_list",
            "objs",
        ]
        candidates = [payload.get(key) for key in direct_keys]
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.extend(self._collect_list_candidates(data))
        return candidates

    def _normalize_item(self, item: dict[str, Any], niche: str) -> NormalizedDouyinVideo:
        if item.get("item_id"):
            return self._normalize_billboard_item(item, niche)
        if item.get("word") and not any(item.get(key) for key in ("aweme_id", "video_id", "share_url")):
            return self._normalize_hot_search_item(item, niche)

        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        video_id = self._str(item.get("aweme_id") or item.get("video_id") or item.get("id"))
        source_url = (
            self._str(item.get("share_url") or item.get("source_url") or item.get("url"))
            or (f"https://www.douyin.com/video/{video_id}" if video_id else "")
        )
        if not source_url:
            raise DouyinProviderError("Provider item does not include source_url or video_id.")

        return NormalizedDouyinVideo(
            video_id=video_id,
            source_url=source_url,
            author_name=self._str(author.get("nickname") or item.get("author_name")),
            author_id=self._str(author.get("uid") or author.get("sec_uid") or item.get("author_id")),
            caption=self._str(item.get("desc") or item.get("caption") or item.get("title")),
            cover_url=self._cover_url(video, item),
            like_count=self._int(stats.get("digg_count") or item.get("like_count")),
            comment_count=self._int(stats.get("comment_count") or item.get("comment_count")),
            share_count=self._int(stats.get("share_count") or item.get("share_count")),
            collect_count=self._int(stats.get("collect_count") or item.get("collect_count")),
            duration=self._duration(video, item),
            create_time=self._int_or_none(item.get("create_time")),
            niche=niche,
        )

    def _normalize_billboard_item(self, item: dict[str, Any], niche: str) -> NormalizedDouyinVideo:
        video_id = self._str(item.get("item_id"))
        if not video_id:
            raise DouyinProviderError("TikHub billboard item does not include item_id.")
        return NormalizedDouyinVideo(
            video_id=video_id,
            source_url=f"https://www.douyin.com/video/{video_id}",
            author_name=self._str(item.get("nick_name")),
            author_id=None,
            caption=self._str(item.get("item_title")),
            cover_url=self._str(item.get("item_cover_url")),
            like_count=self._int(item.get("like_cnt")),
            comment_count=self._int(item.get("comment_cnt")),
            share_count=self._int(item.get("share_cnt")),
            collect_count=self._int(item.get("play_cnt")),
            duration=self._duration({}, {"duration": item.get("item_duration")}),
            create_time=self._int_or_none(item.get("publish_time")),
            niche=niche,
        )

    def _normalize_hot_search_item(self, item: dict[str, Any], niche: str) -> NormalizedDouyinVideo:
        word = self._str(item.get("word"))
        if not word:
            raise DouyinProviderError("TikHub hot search item does not include word.")

        sentence_id = self._str(item.get("sentence_id") or item.get("group_id"))
        source_url = f"https://www.douyin.com/search/{quote(word)}?type=general"
        return NormalizedDouyinVideo(
            video_id=f"hotsearch_{sentence_id}" if sentence_id else None,
            source_url=source_url,
            author_name="Douyin hot search",
            author_id=None,
            caption=word,
            cover_url=self._hot_search_cover_url(item),
            like_count=self._int(item.get("hot_value") or item.get("view_count")),
            comment_count=self._int(item.get("discuss_video_count")),
            share_count=self._int(item.get("video_count")),
            collect_count=0,
            duration=None,
            create_time=self._int_or_none(item.get("event_time")),
            niche=niche,
        )

    def _filter_by_niche(self, items: list[NormalizedDouyinVideo], niche: str) -> list[NormalizedDouyinVideo]:
        terms = [term.casefold() for term in self._category_terms(niche)]
        filtered = [
            item
            for item in items
            if any(term in self._searchable_text(item).casefold() for term in terms)
        ]
        return filtered

    def _category_terms(self, niche: str) -> list[str]:
        terms = CATEGORY_SEARCH_TERMS.get(niche, [niche])
        if niche not in terms:
            return [niche, *terms]
        return terms

    def _searchable_text(self, item: NormalizedDouyinVideo) -> str:
        return " ".join(
            value
            for value in [
                item.video_id,
                item.source_url,
                item.author_name,
                item.author_id,
                item.caption,
            ]
            if value
        )

    def _cover_url(self, video: dict[str, Any], item: dict[str, Any]) -> str | None:
        cover = video.get("cover") if isinstance(video.get("cover"), dict) else {}
        urls = cover.get("url_list") if isinstance(cover.get("url_list"), list) else []
        return self._str(urls[0] if urls else item.get("cover_url"))

    def _hot_search_cover_url(self, item: dict[str, Any]) -> str | None:
        cover = item.get("word_cover")
        if isinstance(cover, str):
            return self._str(cover)
        if not isinstance(cover, dict):
            return None
        urls = cover.get("url_list") if isinstance(cover.get("url_list"), list) else []
        return self._str(urls[0] if urls else cover.get("url"))

    def _duration(self, video: dict[str, Any], item: dict[str, Any]) -> float | None:
        raw = video.get("duration") or item.get("duration")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value / 1000 if value > 1000 else value

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
