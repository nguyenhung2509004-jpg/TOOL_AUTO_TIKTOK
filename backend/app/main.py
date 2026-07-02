import uvicorn
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.douyin_trends import router as douyin_trends_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.database import Base, engine
from app.core.database import SessionLocal
from app.models import video as _video_models
from app.models.video import RenderJob, SourceVideo
from app.services.local_download_watcher import start_local_download_watcher, stop_local_download_watcher


def create_app() -> FastAPI:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title="Douyin Viet Dub Tool", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(douyin_trends_router)

    @app.on_event("startup")
    def maybe_start_local_watcher():
        _mark_interrupted_import_jobs()
        _mark_interrupted_render_jobs()
        if settings.enable_local_watcher:
            start_local_download_watcher()

    @app.on_event("shutdown")
    def shutdown_local_watcher():
        stop_local_download_watcher()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def _mark_interrupted_render_jobs() -> None:
    db = SessionLocal()
    try:
        jobs = db.query(RenderJob).filter(RenderJob.status.in_(["queued", "rendering", "cancel_requested"])).all()
        for job in jobs:
            job.status = "failed"
            job.error_message = "Render was interrupted by backend restart. Start render again."
            job.completed_at = datetime.utcnow()
        if jobs:
            db.commit()
    finally:
        db.close()


def _mark_interrupted_import_jobs() -> None:
    db = SessionLocal()
    try:
        videos = (
            db.query(SourceVideo)
            .filter(SourceVideo.status.in_(["pending", "downloading", "extracting_audio", "transcribing"]))
            .all()
        )
        for video in videos:
            video.status = "failed"
            video.error_message = "Import/ASR was interrupted by backend restart. Click Retry import to process again."
        if videos:
            db.commit()
    finally:
        db.close()


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
