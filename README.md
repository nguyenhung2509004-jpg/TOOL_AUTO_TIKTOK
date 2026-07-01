# Douyin -> Viet Dub -> TikTok Export Tool

MVP auto tool for importing a Douyin video, editing Vietnamese dub segments, generating subtitles, rendering a dubbed export, and preparing TikTok-safe export assets.

## Stack

- Backend: FastAPI, SQLAlchemy, SQLite by default
- Jobs: in-process background jobs for MVP, Celery-ready service boundaries
- Media: FFmpeg + yt-dlp wrappers
- Frontend: React + Vite

## Quick Start

### Docker Backend

```powershell
Copy-Item .env.example .env
docker compose up -d backend
```

Backend health check:

```powershell
curl.exe http://localhost:8000/health
```

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
```

Backend runs at `http://localhost:8000`.

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://127.0.0.1:5173`.

## Required Tools

- FFmpeg must be available on PATH for real rendering.
- yt-dlp must be installed for real Douyin downloads.
- Douyin often requires logged-in browser cookies. Export cookies in Netscape `cookies.txt` format and save them to `storage/cookies/douyin_cookies.txt`.

This build is real-only: failed downloads, missing ASR, missing translation, or missing TTS providers stop the job instead of creating mock data.

## Environment

Copy `.env.example` to `.env` and adjust values.

```powershell
Copy-Item .env.example .env
```

## Current Workflow

1. Preferred: let the Douyin app download MP4 files into `storage/inbox`.
2. Click `Scan inbox` in the frontend to import new local MP4 files.
3. Use the Douyin Trend Dashboard to scan hot ideas through TikHub, open links, and mark one trend as waiting for download.
4. ASR/translation/TTS must be configured with real providers; otherwise the job fails with a clear error.
5. Translate Studio lets you edit Vietnamese text and duration warnings.
6. Render endpoint creates `.srt` and attempts FFmpeg render.
7. Final export can be downloaded from backend.

## Real-Only Mode

Mock transcript, mock translation, and generated test-tone TTS are disabled. A video must have a real `raw_video_path`, real transcript segments, and real TTS voice files before render can complete.

The old test DB was backed up to `storage/backups/tool_tiktok_before_real_only.db` before mock rows were removed.

## Douyin App Watch Folder

Default local folder:

```txt
D:\HUNG\Tool_Tiktok\storage\inbox
```

Then press `Scan inbox` in the web UI. The backend imports each new `.mp4`, `.mov`, `.mkv`, or `.webm` file exactly once by `raw_video_path`.

For Docker, `DOUYIN_LOCAL_DOWNLOAD_DIR` is the host folder mounted into the backend as `/downloads`. To use the real Douyin app download folder, set this in `.env`:

```txt
DOUYIN_LOCAL_DOWNLOAD_DIR=D:\DouyinDownloads
```

Then restart:

```powershell
docker compose up -d --no-build backend
```

## TikHub Trend Discovery

Set these in `.env`:

```txt
TIKHUB_API_KEY=your_key_here
TIKHUB_BASE_URL=https://api.tikhub.io
TIKHUB_HOT_SEARCH_PATH=/api/v1/douyin/web/fetch_hot_search_list
```

The endpoint path is isolated because TikHub API paths can differ by plan/version. If scan returns a response-shape error, update `TIKHUB_HOT_SEARCH_PATH` or the parser in `backend/app/services/douyin_provider.py`.

## Semi-Automatic Trend Flow

1. Open the Trend Dashboard.
2. Pick a niche and click `Quet video hot`.
3. Click `Open Douyin`.
4. Click `Cho tai` on the trend you plan to download.
5. Download the video manually in the Douyin app/browser into the configured folder.
6. If `ENABLE_LOCAL_WATCHER=true`, the backend watcher attaches the next stable MP4 to the waiting trend.
7. If watcher is off, click `Scan inbox`, or use `Gan file` and paste a backend-visible file path.

No TikTok auto-posting, anti-bot bypass, watermark removal, or cookie storage is implemented in this phase.

## Manual Test Checklist

1. Backend starts without `TIKHUB_API_KEY`.
2. `GET /api/douyin/trends/niches` returns niche list.
3. `POST /api/douyin/trends/scan` returns clear config error without `TIKHUB_API_KEY`.
4. With a valid provider key/path, scan saves trends in SQLite.
5. `GET /api/douyin/trends` returns saved records.
6. Mark a trend as `waiting_download`.
7. Copy a test MP4 into `DOUYIN_LOCAL_DOWNLOAD_DIR`.
8. Watcher waits until file size is stable.
9. Watcher attaches MP4 to the waiting trend.
10. Duplicate file is not imported twice.
11. Frontend shows trend status updates.

## Security Notes

- Do not commit `.env`.
- Do not commit cookies or downloaded videos.
- Do not put provider API keys in frontend code.
- If you pasted account cookies anywhere, rotate/logout that session.

## Local URLs

- Frontend dev server: `http://127.0.0.1:5173/`
- Backend API: `http://localhost:8000`
- Backend docs: `http://localhost:8000/docs`

## Safety Note

TikTok upload automation is intentionally not enabled by default. The safe default is export/download plus caption preparation. Any Playwright draft upload should run locally with user-owned cookies and explicit user action.

## Douyin Cookie Fix

If render says `Raw video missing`, check the import error first. For `Fresh cookies ... are needed`:

1. Open `https://www.douyin.com` in Chrome/Edge.
2. Log in and open the target video page once.
3. Export cookies with a browser extension that produces Netscape `cookies.txt` format.
4. Save the file as `storage/cookies/douyin_cookies.txt`.
5. Retry import in the UI.

The cookie file should contain login/session cookie names such as `sessionid`, `sid_guard`, `passport_csrf_token`, or `odin_tt`. Anonymous cookies are not enough.
