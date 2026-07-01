from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.video import DouyinTrend
from app.schemas.trend import AttachLocalFileRequest, DouyinTrendOut, NicheOut, TrendActionResponse, TrendScanRequest
from app.services.douyin_provider import CATEGORY_SEARCH_TERMS, DouyinProviderError, TikHubClient
from app.services.trends import attach_local_file_to_trend, enqueue_video_processing_for_trend, upsert_trend

router = APIRouter(prefix="/api/douyin/trends", tags=["douyin-trends"])

NICHES = [
    {"label_vi": "Meo vat", "keyword_cn": "\u751f\u6d3b\u6280\u5de7"},
    {"label_vi": "Do an", "keyword_cn": "\u7f8e\u98df"},
    {"label_vi": "Thu cung", "keyword_cn": "\u5ba0\u7269"},
    {"label_vi": "Cong nghe", "keyword_cn": "\u79d1\u6280"},
    {"label_vi": "Review san pham", "keyword_cn": "\u6d4b\u8bc4"},
    {"label_vi": "Hai huoc", "keyword_cn": "\u641e\u7b11"},
    {"label_vi": "Hoc tap", "keyword_cn": "\u5b66\u4e60"},
    {"label_vi": "Lam dep", "keyword_cn": "\u7f8e\u5986"},
    {"label_vi": "Du lich", "keyword_cn": "\u65c5\u884c"},
    {"label_vi": "Me va be", "keyword_cn": "\u6bcd\u5a74"},
    {"label_vi": "The thao", "keyword_cn": "\u8fd0\u52a8"},
    {"label_vi": "Xe co", "keyword_cn": "\u6c7d\u8f66"},
]


@router.post("/scan", response_model=list[DouyinTrendOut])
async def scan_trends(payload: TrendScanRequest, db: Session = Depends(get_db)):
    try:
        items = await TikHubClient().search_hot_videos(payload.niche, payload.limit)
    except DouyinProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    trends = [upsert_trend(db, item) for item in items]
    return sorted(trends, key=lambda trend: trend.hot_score, reverse=True)


@router.get("", response_model=list[DouyinTrendOut])
def list_trends(
    status: str | None = None,
    niche: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(DouyinTrend)
    if status:
        query = query.filter(DouyinTrend.status == status)
    if niche:
        query = query.filter(DouyinTrend.niche == niche)
        rows = query.order_by(DouyinTrend.hot_score.desc(), DouyinTrend.created_at.desc()).limit(500).all()
        return [trend for trend in rows if _is_matching_niche(trend, niche)][offset : offset + limit]
    return query.order_by(DouyinTrend.hot_score.desc(), DouyinTrend.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/{trend_id}/waiting-download", response_model=DouyinTrendOut)
def mark_waiting_download(trend_id: int, db: Session = Depends(get_db)):
    trend = _get_trend(db, trend_id)
    db.query(DouyinTrend).filter(DouyinTrend.waiting_download.is_(True)).update({"waiting_download": False})
    trend.status = "waiting_download"
    trend.waiting_download = True
    trend.waiting_since = datetime.utcnow()
    trend.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(trend)
    return trend


@router.post("/{trend_id}/cancel-waiting", response_model=DouyinTrendOut)
def cancel_waiting_download(trend_id: int, db: Session = Depends(get_db)):
    trend = _get_trend(db, trend_id)
    trend.waiting_download = False
    if trend.status == "waiting_download":
        trend.status = "found"
    trend.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(trend)
    return trend


@router.post("/{trend_id}/attach-local-file", response_model=TrendActionResponse)
def attach_local_file(trend_id: int, payload: AttachLocalFileRequest, db: Session = Depends(get_db)):
    trend = _get_trend(db, trend_id)
    try:
        trend = attach_local_file_to_trend(db, trend, Path(payload.file_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TrendActionResponse(trend=trend, message=enqueue_video_processing_for_trend(trend.id))


@router.get("/niches", response_model=list[NicheOut])
def get_niches():
    return NICHES


def _get_trend(db: Session, trend_id: int) -> DouyinTrend:
    trend = db.get(DouyinTrend, trend_id)
    if not trend:
        raise HTTPException(status_code=404, detail="Trend not found")
    return trend


def _is_matching_niche(trend: DouyinTrend, niche: str) -> bool:
    if trend.raw_video_path:
        return True
    if trend.video_id and trend.video_id.startswith(("category_search_", "hotsearch_")):
        return False
    if "/search/" in trend.source_url:
        return False
    terms = CATEGORY_SEARCH_TERMS.get(niche, [niche])
    text = " ".join(
        value
        for value in [trend.video_id, trend.source_url, trend.author_name, trend.author_id, trend.caption]
        if value
    ).casefold()
    return any(term.casefold() in text for term in terms)
