import threading
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.video import DouyinTrend
from app.services.trends import VIDEO_EXTENSIONS, attach_local_file_to_trend, find_waiting_trend


class LocalDownloadWatcher:
    def __init__(self) -> None:
        settings = get_settings()
        self.watch_dir = settings.douyin_local_download_dir
        self.window_minutes = settings.local_watcher_window_minutes
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.seen: set[tuple[str, int]] = set()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._run, name="local-download-watcher", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.scan_once()
            self.stop_event.wait(3)

    def scan_once(self) -> None:
        for path in sorted(self.watch_dir.iterdir()):
            if self.stop_event.is_set():
                return
            if not self._is_candidate(path):
                continue
            stable = self._wait_until_stable(path)
            if not stable:
                continue
            signature = (str(path.resolve()), path.stat().st_size)
            if signature in self.seen:
                continue
            self.seen.add(signature)
            self._attach_or_record_unmatched(path)

    def _is_candidate(self, path: Path) -> bool:
        if not path.is_file():
            return False
        suffix = path.suffix.lower()
        if suffix in {".crdownload", ".tmp", ".part"}:
            return False
        return suffix in VIDEO_EXTENSIONS

    def _wait_until_stable(self, path: Path, checks: int = 3, delay: float = 1.0) -> bool:
        previous = -1
        stable_count = 0
        while stable_count < checks and not self.stop_event.is_set():
            try:
                current = path.stat().st_size
            except OSError:
                return False
            if current > 0 and current == previous:
                stable_count += 1
            else:
                stable_count = 0
            previous = current
            time.sleep(delay)
        return stable_count >= checks

    def _attach_or_record_unmatched(self, path: Path) -> None:
        db = SessionLocal()
        try:
            existing = db.query(DouyinTrend).filter(DouyinTrend.imported_file_name == path.name).first()
            if existing:
                return
            trend = find_waiting_trend(db, self.window_minutes)
            if trend:
                attach_local_file_to_trend(db, trend, path)
                return
            unmatched = DouyinTrend(
                source_url=f"file://{path.resolve()}",
                caption=path.stem,
                status="downloaded",
                raw_video_path=str(path.resolve()),
                imported_file_name=path.name,
                niche="local-unmatched",
            )
            db.add(unmatched)
            db.commit()
        finally:
            db.close()


_watcher: LocalDownloadWatcher | None = None


def start_local_download_watcher() -> LocalDownloadWatcher:
    global _watcher
    if _watcher is None:
        _watcher = LocalDownloadWatcher()
    _watcher.start()
    return _watcher


def stop_local_download_watcher() -> None:
    if _watcher:
        _watcher.stop()
