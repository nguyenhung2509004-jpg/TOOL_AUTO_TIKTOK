import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, DouyinTrend, Niche, RenderJob, Segment, SourceVideo, TTSVoice } from "./lib/api";
import "./styles.css";

type AppTab = "dashboard" | "studio" | "export";
type ExportFilter = "all" | "rendering" | "completed" | "failed" | "canceled";
const TERMINAL_RENDER_STATUSES = new Set(["completed", "failed", "canceled", "cancel_requested"]);

const DEFAULT_TTS_VOICES: TTSVoice[] = [
  { id: "fpt_banmai", label: "FPT - Ban Mai", provider: "fpt_ai", voice_id: "banmai" },
  { id: "fpt_leminh", label: "FPT - Le Minh", provider: "fpt_ai", voice_id: "leminh" },
];

function App() {
  const [tab, setTab] = useState<AppTab>("dashboard");
  const [url, setUrl] = useState("");
  const [videos, setVideos] = useState<SourceVideo[]>([]);
  const [activeVideo, setActiveVideo] = useState<SourceVideo | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [job, setJob] = useState<RenderJob | null>(null);
  const [jobs, setJobs] = useState<RenderJob[]>([]);
  const [caption, setCaption] = useState("");
  const [volume, setVolume] = useState(0.15);
  const [voiceVolume, setVoiceVolume] = useState(1);
  const [ttsVoices, setTtsVoices] = useState<TTSVoice[]>(DEFAULT_TTS_VOICES);
  const [selectedVoiceId, setSelectedVoiceId] = useState(DEFAULT_TTS_VOICES[0].id);
  const [speechSpeed, setSpeechSpeed] = useState(1);
  const [pitch, setPitch] = useState(0);
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const [folders, setFolders] = useState(["All Projects", "Food tests", "Product reviews"]);
  const [activeFolder, setActiveFolder] = useState("All Projects");
  const [exportFilter, setExportFilter] = useState<ExportFilter>("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [niches, setNiches] = useState<Niche[]>([]);
  const [selectedNiche, setSelectedNiche] = useState("");
  const [trends, setTrends] = useState<DouyinTrend[]>([]);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [trendBusy, setTrendBusy] = useState(false);

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2200);
  }

  async function refreshVideos(selectId?: number) {
    const nextVideos = await api.videos();
    setVideos(nextVideos);
    const nextActive = nextVideos.find((item) => item.id === (selectId ?? activeVideo?.id)) ?? nextVideos[0] ?? null;
    setActiveVideo(nextActive);
    return nextActive;
  }

  async function refreshJobs() {
    const nextJobs = await api.renderJobs();
    setJobs(nextJobs);
    setJob((current) => {
      if (!nextJobs.length) return null;
      if (!current) return nextJobs[0];
      return nextJobs.find((item) => item.id === current.id) ?? nextJobs[0];
    });
    return nextJobs;
  }

  async function importVideo(event?: React.FormEvent) {
    event?.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.importDouyin(url.trim());
      setUrl("");
      await refreshVideos(response.video_id);
      setTab("studio");
      showNotice(response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadLocalVideo(file: File) {
    setBusy(true);
    setError(null);
    try {
      const response = await api.uploadLocal(file);
      await refreshVideos(response.video_id);
      setTab("studio");
      showNotice(response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload local video failed");
    } finally {
      setBusy(false);
    }
  }

  async function scanLocalInbox() {
    setBusy(true);
    setError(null);
    try {
      const response = await api.scanLocal();
      const selectedId = response.imported[0]?.video_id;
      await refreshVideos(selectedId);
      if (selectedId) setTab("studio");
      showNotice(
        response.imported.length
          ? `Imported ${response.imported.length} local video(s).`
          : `No new MP4 found in ${response.watch_dir}. Skipped: ${response.skipped.length}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan local folder failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveSegments() {
    if (!activeVideo) return;
    setBusy(true);
    setError(null);
    try {
      setSegments(await api.updateSegments(activeVideo.id, segments));
      showNotice("Segments saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function updateActiveVideo(payload: { source_url?: string; caption_original?: string }) {
    if (!activeVideo) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.updateVideo(activeVideo.id, payload);
      setActiveVideo(updated);
      setVideos((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      showNotice("Video updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update video failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteActiveVideo() {
    if (!activeVideo) return;
    const ok = window.confirm(`Delete Video #${activeVideo.id}? This also removes stored segments and render job records.`);
    if (!ok) return;
    setBusy(true);
    setError(null);
    try {
      const deletedId = activeVideo.id;
      const response = await api.deleteVideo(deletedId);
      const remaining = videos.filter((video) => video.id !== deletedId);
      setVideos(remaining);
      setActiveVideo(remaining[0] ?? null);
      setSegments([]);
      setCaption("");
      showNotice(`${response.message}. Deleted files: ${response.deleted_files}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete video failed");
    } finally {
      setBusy(false);
    }
  }

  async function retryImport() {
    if (!activeVideo) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.reimport(activeVideo.id);
      await refreshVideos(response.video_id);
      showNotice(response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry import failed");
    } finally {
      setBusy(false);
    }
  }

  async function startRender() {
    if (!activeVideo) return;
    setBusy(true);
    setError(null);
    try {
      const voice = ttsVoices.find((item) => item.id === selectedVoiceId) ?? ttsVoices[0] ?? DEFAULT_TTS_VOICES[0];
      const nextJob = await api.render(activeVideo.id, volume, burnSubtitles, {
        ttsProvider: voice.provider,
        voiceId: voice.voice_id,
        voiceVolume,
      });
      setJob(nextJob);
      setJobs((items) => [nextJob, ...items.filter((item) => item.id !== nextJob.id)]);
      setTab("export");
      showNotice(`Render queued with ${voice.label}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Render failed");
    } finally {
      setBusy(false);
    }
  }

  async function loadCaption(copy = false) {
    if (!activeVideo) return;
    setError(null);
    try {
      const response = await api.caption(activeVideo.id);
      setCaption(response.caption);
      if (copy && navigator.clipboard) {
        await navigator.clipboard.writeText(response.caption);
        showNotice("Caption copied.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Caption failed");
    }
  }

  async function cancelRender(jobId: number) {
    setError(null);
    try {
      const response = await api.cancelRenderJob(jobId);
      setJob((current) => (current?.id === response.job_id ? null : current));
      setJobs((items) => items.filter((item) => item.id !== response.job_id));
      showNotice(response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cancel render failed");
    }
  }

  async function cleanupFiles() {
    if (!activeVideo) return;
    setError(null);
    try {
      const response = await api.cleanup(activeVideo.id);
      showNotice(`Cleanup done: ${response.deleted_files} deleted, ${response.kept_files} kept.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cleanup failed");
    }
  }

  async function loadTrends(niche = selectedNiche) {
    setTrendBusy(true);
    setTrendError(null);
    try {
      setTrends(await api.trends({ niche: niche || undefined }));
    } catch (err) {
      setTrendError(err instanceof Error ? err.message : "Cannot load trends");
    } finally {
      setTrendBusy(false);
    }
  }

  async function scanTrends() {
    if (!selectedNiche) return;
    setTrendBusy(true);
    setTrendError(null);
    try {
      const nextTrends = await api.scanTrends(selectedNiche, 12);
      setTrends(nextTrends);
      showNotice(`Loaded ${nextTrends.length} real Douyin video(s).`);
    } catch (err) {
      setTrendError(err instanceof Error ? err.message : "Trend scan failed");
    } finally {
      setTrendBusy(false);
    }
  }

  async function updateTrend(action: () => Promise<DouyinTrend>) {
    setTrendBusy(true);
    setTrendError(null);
    try {
      const updated = await action();
      setTrends((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      showNotice(updated.waiting_download ? "Trend marked for download." : "Trend updated.");
    } catch (err) {
      setTrendError(err instanceof Error ? err.message : "Trend action failed");
    } finally {
      setTrendBusy(false);
    }
  }

  async function attachFileToTrend(trend: DouyinTrend) {
    const filePath = window.prompt("Paste full local path visible to backend, for example D:\\DouyinDownloads\\video.mp4");
    if (!filePath) return;
    setTrendBusy(true);
    setTrendError(null);
    try {
      const response = await api.attachTrendFile(trend.id, filePath);
      setTrends((items) => items.map((item) => (item.id === response.trend.id ? response.trend : item)));
      showNotice(response.message);
    } catch (err) {
      setTrendError(err instanceof Error ? err.message : "Attach file failed");
    } finally {
      setTrendBusy(false);
    }
  }

  function addFolder() {
    const name = window.prompt("Folder name");
    const normalized = name?.trim();
    if (!normalized || folders.includes(normalized)) return;
    setFolders((items) => [...items, normalized]);
    setActiveFolder(normalized);
    showNotice(`Folder created: ${normalized}`);
  }

  useEffect(() => {
    refreshVideos().catch((err) => setError(err instanceof Error ? err.message : "Cannot load videos"));
    refreshJobs().catch((err) => setError(err instanceof Error ? err.message : "Cannot load render history"));
    api.ttsVoices()
      .then((items) => {
        const nextVoices = items.length ? items : DEFAULT_TTS_VOICES;
        setTtsVoices(nextVoices);
        setSelectedVoiceId((current) => nextVoices.some((voice) => voice.id === current) ? current : nextVoices[0].id);
      })
      .catch(() => setTtsVoices(DEFAULT_TTS_VOICES));
    api.niches()
      .then((items) => {
        setNiches(items);
        const first = items[0]?.keyword_cn ?? "";
        setSelectedNiche(first);
        return api.trends({ niche: first || undefined });
      })
      .then(setTrends)
      .catch((err) => setTrendError(err instanceof Error ? err.message : "Cannot load trends"));
  }, []);

  useEffect(() => {
    if (!activeVideo) {
      setSegments([]);
      setCaption("");
      return;
    }
    api.segments(activeVideo.id).then(setSegments).catch(() => setSegments([]));
    api.caption(activeVideo.id).then((response) => setCaption(response.caption)).catch(() => setCaption(""));
  }, [activeVideo?.id, activeVideo?.status]);

  useEffect(() => {
    if (!activeVideo || activeVideo.status === "ready" || activeVideo.status === "failed") return;
    const timer = window.setInterval(() => {
      refreshVideos(activeVideo.id).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeVideo?.id, activeVideo?.status]);

  useEffect(() => {
    if (!jobs.some((item) => !TERMINAL_RENDER_STATUSES.has(item.status))) return;
    const timer = window.setInterval(() => {
      refreshJobs().catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [jobs]);

  const warningCount = useMemo(() => segments.filter((segment) => segment.warning).length, [segments]);
  const visibleVideos = activeFolder === "All Projects"
    ? videos
    : videos.filter((video) => (video.caption_original || `Video ${video.id}`).toLowerCase().includes(activeFolder.toLowerCase()));
  const storagePercent = Math.min(82, Math.max(24, videos.length * 9 + segments.length));

  return (
    <div className="appFrame">
      <Sidebar
        tab={tab}
        setTab={setTab}
        videos={videos}
        storagePercent={storagePercent}
        folders={folders}
        activeFolder={activeFolder}
        setActiveFolder={setActiveFolder}
        addFolder={addFolder}
      />
      <main className="mainArea">
        <Topbar
          tab={tab}
          setTab={setTab}
          url={url}
          setUrl={setUrl}
          busy={busy}
          importVideo={importVideo}
          uploadLocalVideo={uploadLocalVideo}
        />
        {(error || trendError || notice) && <div className={notice ? "alert success" : "alert"}>{notice || error || trendError}</div>}

        {tab === "dashboard" && (
          <DashboardView
            trends={trends}
            niches={niches}
            selectedNiche={selectedNiche}
            setSelectedNiche={setSelectedNiche}
            trendBusy={trendBusy}
            scanTrends={scanTrends}
            loadTrends={loadTrends}
            updateTrend={updateTrend}
            attachFileToTrend={attachFileToTrend}
            showNotice={showNotice}
          />
        )}

        {tab === "studio" && (
          <StudioView
            activeVideo={activeVideo}
            videos={visibleVideos}
            segments={segments}
            setSegments={setSegments}
            setActiveVideo={setActiveVideo}
            warningCount={warningCount}
            busy={busy}
            saveSegments={saveSegments}
            refreshVideos={() => refreshVideos(activeVideo?.id)}
            updateActiveVideo={updateActiveVideo}
            deleteActiveVideo={deleteActiveVideo}
            retryImport={retryImport}
            startRender={startRender}
            volume={volume}
            setVolume={setVolume}
            voiceVolume={voiceVolume}
            setVoiceVolume={setVoiceVolume}
            ttsVoices={ttsVoices}
            selectedVoiceId={selectedVoiceId}
            setSelectedVoiceId={setSelectedVoiceId}
            speechSpeed={speechSpeed}
            setSpeechSpeed={setSpeechSpeed}
            pitch={pitch}
            setPitch={setPitch}
            burnSubtitles={burnSubtitles}
            setBurnSubtitles={setBurnSubtitles}
            showNotice={showNotice}
          />
        )}

        {tab === "export" && (
          <ExportView
            videos={visibleVideos}
            activeVideo={activeVideo}
            job={job}
            jobs={jobs}
            busy={busy}
            scanLocalInbox={scanLocalInbox}
            startRender={startRender}
            loadCaption={loadCaption}
            cleanupFiles={cleanupFiles}
            caption={caption}
            exportFilter={exportFilter}
            setExportFilter={setExportFilter}
            storagePercent={storagePercent}
            showNotice={showNotice}
            cancelRender={cancelRender}
          />
        )}
      </main>
      <button className="assistantFab" type="button" aria-label="Assistant tools">*</button>
    </div>
  );
}

function Sidebar({
  tab,
  setTab,
  videos,
  storagePercent,
  folders,
  activeFolder,
  setActiveFolder,
  addFolder,
}: {
  tab: AppTab;
  setTab: (tab: AppTab) => void;
  videos: SourceVideo[];
  storagePercent: number;
  folders: string[];
  activeFolder: string;
  setActiveFolder: (folder: string) => void;
  addFolder: () => void;
}) {
  return (
    <aside className="sideRail">
      <div className="brand">StudioSync</div>
      <div className="libraryHead">
        <div className="libraryIcon"><Icon name="library" /></div>
        <div>
          <strong>Library</strong>
          <span>Manage assets</span>
        </div>
      </div>
      <button className="folderBtn" onClick={addFolder} type="button">+ New Folder</button>
      <div className="folderList">
        {folders.map((folder) => (
          <button className={activeFolder === folder ? "active" : ""} key={folder} onClick={() => setActiveFolder(folder)} type="button">
            {folder}
          </button>
        ))}
      </div>
      <nav className="sideNav">
        <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")} type="button">
          <Icon name="grid" /> All Projects
        </button>
        <button className={tab === "studio" ? "active" : ""} onClick={() => setTab("studio")} type="button">
          <Icon name="clock" /> Studio
        </button>
        <button className={tab === "export" ? "active" : ""} onClick={() => setTab("export")} type="button">
          <Icon name="export" /> Export
        </button>
      </nav>
      <div className="sideBottom">
        <button type="button">? Help</button>
        <div className="storageLine">
          <span>Storage</span>
          <small>{storagePercent}%</small>
        </div>
        <div className="storageTrack"><span style={{ width: `${storagePercent}%` }} /></div>
        <small>{videos.length} imported videos</small>
      </div>
    </aside>
  );
}

function Icon({ name }: { name: "library" | "grid" | "clock" | "export" }) {
  if (name === "clock") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" />
        <path d="M12 7v5l3 2" />
      </svg>
    );
  }
  if (name === "export") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 19h14" />
        <path d="M12 5v10" />
        <path d="m8 9 4-4 4 4" />
      </svg>
    );
  }
  if (name === "library") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5h14v14H5z" />
        <path d="M9 9h6v6H9z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 5h6v6H5z" />
      <path d="M13 5h6v6h-6z" />
      <path d="M5 13h6v6H5z" />
      <path d="M13 13h6v6h-6z" />
    </svg>
  );
}

function Topbar({
  tab,
  setTab,
  url,
  setUrl,
  busy,
  importVideo,
  uploadLocalVideo,
}: {
  tab: AppTab;
  setTab: (tab: AppTab) => void;
  url: string;
  setUrl: (value: string) => void;
  busy: boolean;
  importVideo: (event?: React.FormEvent) => Promise<void>;
  uploadLocalVideo: (file: File) => Promise<void>;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function handleImportClick() {
    if (url.trim()) {
      importVideo();
      return;
    }
    fileInputRef.current?.click();
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    uploadLocalVideo(file);
  }

  return (
    <header className="topNav">
      <nav className="sectionTabs">
        <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")} type="button">Dashboard</button>
        <button className={tab === "studio" ? "active" : ""} onClick={() => setTab("studio")} type="button">Studio</button>
        <button className={tab === "export" ? "active" : ""} onClick={() => setTab("export")} type="button">Export</button>
      </nav>
      <form className="searchImport" onSubmit={importVideo}>
        <span>Search</span>
        <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="Paste Douyin URL here..." />
      </form>
      <div className="topActions">
        <button className="iconBtn" type="button" aria-label="Notifications">N</button>
        <button className="iconBtn" type="button" aria-label="Settings">S</button>
        <input
          ref={fileInputRef}
          className="hiddenFileInput"
          accept="video/mp4,video/quicktime,video/x-matroska,video/webm"
          onChange={handleFileChange}
          type="file"
        />
        <button
          className="importBtn"
          disabled={busy}
          onClick={handleImportClick}
          title={url.trim() ? "Import Douyin URL" : "Choose a local video file"}
          type="button"
        >
          + Import
        </button>
        <div className="avatar" aria-label="Current user">HS</div>
      </div>
    </header>
  );
}

function DashboardView({
  trends,
  niches,
  selectedNiche,
  setSelectedNiche,
  trendBusy,
  scanTrends,
  loadTrends,
  updateTrend,
  attachFileToTrend,
  showNotice,
}: {
  trends: DouyinTrend[];
  niches: Niche[];
  selectedNiche: string;
  setSelectedNiche: (value: string) => void;
  trendBusy: boolean;
  scanTrends: () => Promise<void>;
  loadTrends: (niche?: string) => Promise<void>;
  updateTrend: (action: () => Promise<DouyinTrend>) => Promise<void>;
  attachFileToTrend: (trend: DouyinTrend) => Promise<void>;
  showNotice: (message: string) => void;
}) {
  const visibleTrends = trends.slice(0, 12);

  return (
    <section className="pagePanel dashboardPage">
      <div className="pageHeader">
        <div>
          <h1>Douyin hot search</h1>
          <p>Find real trending Douyin videos, inspect metrics, then save one into the project workflow.</p>
        </div>
        <div className="headerControls">
          <select
            value={selectedNiche}
            onChange={(event) => {
              setSelectedNiche(event.target.value);
              loadTrends(event.target.value).catch(() => undefined);
            }}
          >
            {niches.map((niche) => (
              <option key={niche.keyword_cn} value={niche.keyword_cn}>
                {niche.label_vi} - {niche.keyword_cn}
              </option>
            ))}
          </select>
          <button className="lineBtn" onClick={scanTrends} disabled={trendBusy || !selectedNiche} type="button">
            {trendBusy ? "Refreshing..." : "Refresh trends"}
          </button>
        </div>
      </div>

      <div className="trendShelf">
        {visibleTrends.map((trend, index) => (
          <TrendCard
            key={trend.id}
            trend={trend}
            index={index}
            trendBusy={trendBusy}
            updateTrend={updateTrend}
            attachFileToTrend={attachFileToTrend}
            showNotice={showNotice}
          />
        ))}
        {visibleTrends.length === 0 && (
          <div className="emptyState">
            <strong>No videos in this category yet</strong>
            <span>Choose a category and refresh trends to pull real Douyin video cards.</span>
          </div>
        )}
      </div>
    </section>
  );
}

function TrendCard({
  trend,
  index,
  trendBusy,
  updateTrend,
  attachFileToTrend,
  showNotice,
}: {
  trend: DouyinTrend;
  index: number;
  trendBusy: boolean;
  updateTrend: (action: () => Promise<DouyinTrend>) => Promise<void>;
  attachFileToTrend: (trend: DouyinTrend) => Promise<void>;
  showNotice: (message: string) => void;
}) {
  async function copyLink() {
    await navigator.clipboard?.writeText(trend.source_url);
    showNotice("Douyin video link copied.");
  }

  return (
    <article className="trendCard">
      <div className="thumbWrap">
        {trend.cover_url ? <img src={trend.cover_url} alt={trend.caption || "Douyin video cover"} /> : <div className="realCoverMissing">No real cover</div>}
        <span className="foundFlag">{trend.status === "waiting_download" ? "WAITING" : trend.raw_video_path ? "READY" : "FOUND"}</span>
        <span className="rankFlag">Trending #{index + 1}</span>
        <div className="thumbStats">
          <span>Like {formatNumber(trend.like_count)}</span>
          <span>Hot {formatNumber(trend.hot_score)}</span>
        </div>
      </div>
      <div className="trendCopy">
        <h2>{trend.caption || "Douyin video"}</h2>
        <p>{trend.author_name || "Unknown author"} - {trend.niche || "Category"}</p>
      </div>
      <div className="metricGrid">
        <span><strong>{formatNumber(trend.like_count)}</strong>Like</span>
        <span><strong>{formatNumber(trend.comment_count)}</strong>Comment</span>
        <span><strong>{formatNumber(trend.share_count)}</strong>Share</span>
        <span><strong>{formatNumber(trend.hot_score)}</strong>Hot</span>
      </div>
      <div className="cardActions">
        <button className="miniBtn" onClick={() => window.open(trend.source_url, "_blank")} type="button">Open Douyin</button>
        <button className="miniBtn" onClick={copyLink} type="button">Copy link</button>
        {trend.waiting_download ? (
          <button className="miniBtn" onClick={() => updateTrend(() => api.cancelWaitTrend(trend.id))} disabled={trendBusy} type="button">Cancel wait</button>
        ) : (
          <button className="miniBtn" onClick={() => updateTrend(() => api.waitTrend(trend.id))} disabled={trendBusy} type="button">Save to library</button>
        )}
        <button className="miniBtn" onClick={() => attachFileToTrend(trend)} disabled={trendBusy} type="button">Attach MP4</button>
      </div>
    </article>
  );
}

function StudioView({
  activeVideo,
  videos,
  segments,
  setSegments,
  setActiveVideo,
  warningCount,
  busy,
  saveSegments,
  refreshVideos,
  updateActiveVideo,
  deleteActiveVideo,
  retryImport,
  startRender,
  volume,
  setVolume,
  voiceVolume,
  setVoiceVolume,
  ttsVoices,
  selectedVoiceId,
  setSelectedVoiceId,
  speechSpeed,
  setSpeechSpeed,
  pitch,
  setPitch,
  burnSubtitles,
  setBurnSubtitles,
  showNotice,
}: {
  activeVideo: SourceVideo | null;
  videos: SourceVideo[];
  segments: Segment[];
  setSegments: React.Dispatch<React.SetStateAction<Segment[]>>;
  setActiveVideo: (video: SourceVideo) => void;
  warningCount: number;
  busy: boolean;
  saveSegments: () => Promise<void>;
  refreshVideos: () => Promise<SourceVideo | null>;
  updateActiveVideo: (payload: { source_url?: string; caption_original?: string }) => Promise<void>;
  deleteActiveVideo: () => Promise<void>;
  retryImport: () => Promise<void>;
  startRender: () => Promise<void>;
  volume: number;
  setVolume: (value: number) => void;
  voiceVolume: number;
  setVoiceVolume: (value: number) => void;
  ttsVoices: TTSVoice[];
  selectedVoiceId: string;
  setSelectedVoiceId: (value: string) => void;
  speechSpeed: number;
  setSpeechSpeed: (value: number) => void;
  pitch: number;
  setPitch: (value: number) => void;
  burnSubtitles: boolean;
  setBurnSubtitles: (value: boolean) => void;
  showNotice: (message: string) => void;
}) {
  function applyOptimizedText() {
    setSegments((items) => items.map((segment) => ({ ...segment, text_vi: segment.text_vi_optimized || segment.text_vi })));
    showNotice("Optimized text applied to Vietnamese dub column.");
  }

  function renameVideo() {
    if (!activeVideo) return;
    const nextName = window.prompt("Video title / library name", activeVideo.caption_original || `Video ${activeVideo.id}`);
    if (nextName === null) return;
    updateActiveVideo({ caption_original: nextName });
  }

  function editSourceUrl() {
    if (!activeVideo) return;
    const nextUrl = window.prompt("Source URL", activeVideo.source_url);
    if (nextUrl === null) return;
    updateActiveVideo({ source_url: nextUrl });
  }

  return (
    <section className="studioLayout">
      <div className="pagePanel studioTablePanel">
        <div className="studioHeader">
          <div>
            <h1>Translate Studio</h1>
            <span className="fileTag">{activeVideo ? `VIDEO_${activeVideo.id}.mp4` : "No video selected"}</span>
            <span className="draftTag">{activeVideo?.status ?? "Draft"}</span>
          </div>
          <div className="editorTools">
            <button className="lineBtn" onClick={applyOptimizedText} disabled={segments.length === 0} type="button">Apply AI suggestion</button>
            <button className="lineBtn" onClick={saveSegments} disabled={!activeVideo || busy || segments.length === 0} type="button">Save text</button>
            <span>{warningCount} timing warnings</span>
          </div>
        </div>

        <div className="videoPicker">
          <div className="videoCrudBar">
            <button className="lineBtn" onClick={() => refreshVideos()} disabled={busy} type="button">Refresh list</button>
            <button className="lineBtn" onClick={renameVideo} disabled={!activeVideo || busy} type="button">Rename</button>
            <button className="lineBtn" onClick={editSourceUrl} disabled={!activeVideo || busy} type="button">Edit source</button>
            <button className="lineBtn danger" onClick={deleteActiveVideo} disabled={!activeVideo || busy} type="button">Delete</button>
          </div>
          {videos.map((video) => (
            <button className={activeVideo?.id === video.id ? "active" : ""} key={video.id} onClick={() => setActiveVideo(video)} type="button">
              Video #{video.id}<small>{video.status}</small>
            </button>
          ))}
          {videos.length === 0 && <span className="emptyInline">No videos in this library folder.</span>}
        </div>

        {activeVideo?.error_message && (
          <div className="downloadIssue">
            <strong>{activeVideo.raw_video_path ? "Processing failed" : "Raw video missing"}</strong>
            <small>{activeVideo.error_message}</small>
            <button className="lineBtn" onClick={retryImport} disabled={busy} type="button">Retry import</button>
          </div>
        )}

        <div className="segmentTable">
          <div className="segmentRow head">
            <span>Time</span>
            <span>Chinese source</span>
            <span>Vietnamese dub</span>
            <span>Optimized</span>
            <span />
          </div>
          {segments.map((segment, index) => (
            <div className={`segmentRow ${segment.warning ? "needsWork" : ""}`} key={segment.id}>
              <span className="timeCode">{formatTime(segment.start_time)} - {formatTime(segment.end_time)}</span>
              <p>{segment.text_cn}</p>
              <textarea value={segment.text_vi ?? ""} onChange={(event) => updateSegment(index, "text_vi", event.target.value, segments, setSegments)} />
              <textarea value={segment.text_vi_optimized ?? ""} onChange={(event) => updateSegment(index, "text_vi_optimized", event.target.value, segments, setSegments)} />
              <span className={segment.warning ? "checkMark warn" : "checkMark"}>{segment.warning ? "!" : "OK"}</span>
            </div>
          ))}
          {activeVideo && segments.length === 0 && <p className="emptyState inline">Segments are loading or unavailable.</p>}
          {!activeVideo && <p className="emptyState inline">Import or scan a local MP4 to start translating.</p>}
        </div>
      </div>

      <aside className="previewPanel">
        <strong>Video Preview</strong>
        <div className="phonePreview">
          {activeVideo?.raw_video_path ? (
            <video controls src={api.rawVideoUrl(activeVideo.id)} />
          ) : (
            <div className="previewGrid">{Array.from({ length: 12 }).map((_, index) => <span key={index} />)}</div>
          )}
        </div>
        <label className="toggleLine">
          Burn subtitles
          <input type="checkbox" checked={burnSubtitles} onChange={(event) => setBurnSubtitles(event.target.checked)} />
        </label>
        <label className="rangeLine">
          <span>Original audio {Math.round(volume * 100)}%</span>
          <input min="0" max="1" step="0.01" type="range" value={volume} onChange={(event) => setVolume(Number(event.target.value))} />
        </label>
        <label className="rangeLine">
          <span>Voice volume {Math.round(voiceVolume * 100)}%</span>
          <input min="0" max="2" step="0.05" type="range" value={voiceVolume} onChange={(event) => setVoiceVolume(Number(event.target.value))} />
        </label>
        <label>
          Voice Profile
          <select value={selectedVoiceId} onChange={(event) => setSelectedVoiceId(event.target.value)}>
            {ttsVoices.map((voice) => <option value={voice.id} key={voice.id}>{voice.label}</option>)}
          </select>
        </label>
        <label className="rangeLine">
          <span>Speed {speechSpeed.toFixed(2)}x</span>
          <input min="0.75" max="1.35" step="0.05" type="range" value={speechSpeed} onChange={(event) => setSpeechSpeed(Number(event.target.value))} />
        </label>
        <label className="rangeLine">
          <span>Pitch {pitch > 0 ? "+" : ""}{pitch}</span>
          <input min="-4" max="4" step="1" type="range" value={pitch} onChange={(event) => setPitch(Number(event.target.value))} />
        </label>
        <small className="settingsNote">Speed and pitch are saved in the session UI. Backend render currently uses provider voice, audio volume, voice volume, and subtitle settings.</small>
        <button className="renderBtn" onClick={startRender} disabled={!activeVideo || busy || segments.length === 0} type="button">Render video</button>
      </aside>
    </section>
  );
}

function ExportView({
  videos,
  activeVideo,
  job,
  jobs,
  busy,
  scanLocalInbox,
  startRender,
  loadCaption,
  cleanupFiles,
  caption,
  exportFilter,
  setExportFilter,
  storagePercent,
  showNotice,
  cancelRender,
}: {
  videos: SourceVideo[];
  activeVideo: SourceVideo | null;
  job: RenderJob | null;
  jobs: RenderJob[];
  busy: boolean;
  scanLocalInbox: () => Promise<void>;
  startRender: () => Promise<void>;
  loadCaption: (copy?: boolean) => Promise<void>;
  cleanupFiles: () => Promise<void>;
  caption: string;
  exportFilter: ExportFilter;
  setExportFilter: (filter: ExportFilter) => void;
  storagePercent: number;
  showNotice: (message: string) => void;
  cancelRender: (jobId: number) => Promise<void>;
}) {
  const latestJob = jobs[0] ?? job;
  const activeRenderJob = jobs.find((item) => item.status === "queued" || item.status === "rendering") ?? null;
  const renderRows = jobs
    .filter((item) => exportFilter === "all" || item.status === exportFilter)
    .slice(0, 12)
    .map((item) => ({ job: item, video: videos.find((video) => video.id === item.video_id) ?? null }));
  const progress = activeRenderJob?.progress_percentage ?? 0;
  const queueVideo = activeRenderJob ? videos.find((video) => video.id === activeRenderJob.video_id) ?? activeVideo : null;
  const completedCount = jobs.filter((item) => item.status === "completed").length;
  const activeCount = jobs.filter((item) => !TERMINAL_RENDER_STATUSES.has(item.status)).length;

  async function shareCurrent() {
    if (!activeVideo) return;
    const text = caption || activeVideo.caption_original || `Video ${activeVideo.id}`;
    if (navigator.share) {
      await navigator.share({ title: "StudioSync export", text });
    } else {
      await navigator.clipboard?.writeText(text);
      showNotice("Share text copied.");
    }
  }

  return (
    <section className="pagePanel exportPage">
      <div className="pageHeader">
        <div>
          <h1>Quan ly Xuat ban</h1>
          <p>Theo doi render, tai file, copy caption va don dep luu tru.</p>
        </div>
        <div className="headerControls">
          <select value={exportFilter} onChange={(event) => setExportFilter(event.target.value as ExportFilter)}>
            <option value="all">All projects</option>
            <option value="rendering">Rendering</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="canceled">Canceled</option>
          </select>
          <button className="lineBtn" onClick={scanLocalInbox} disabled={busy} type="button">Scan inbox</button>
        </div>
      </div>

      <div className="exportStats">
        <div><strong>{videos.length}</strong><span>Library videos</span></div>
        <div><strong>{completedCount}</strong><span>Completed renders</span></div>
        <div><strong>{activeCount ? `${activeCount} active` : "idle"}</strong><span>Render queue</span></div>
        <div><strong>{storagePercent}%</strong><span>Storage used</span></div>
      </div>

      <div className="historyHeader compact">
        <h2 className="sectionTitle">Hang doi Render</h2>
        {activeRenderJob && <span>Job #{activeRenderJob.id}</span>}
      </div>
      <div className="renderQueue">
        <RenderQueueCard
          name={queueVideo ? `Video_${queueVideo.id}.mp4` : "No selected video"}
          progress={progress}
          eta={activeRenderJob ? `${activeRenderJob.status} - ${activeRenderJob.progress_percentage}%` : "No active render"}
          job={activeRenderJob}
          cancelRender={cancelRender}
        />
      </div>

      <div className="historyHeader">
        <h2 className="sectionTitle">Lich su Du an</h2>
        <span>{renderRows.length} item(s)</span>
      </div>
      <div className="historyTable">
        <div className="historyRow head"><span>Ten video</span><span>Nguon</span><span>Trang thai</span><span>Thao tac</span></div>
        {renderRows.map(({ job: rowJob, video }) => (
          <div className="historyRow" key={rowJob.id}>
            <span className="historyName">
              <strong>{video?.caption_original || `Video_${rowJob.video_id}.mp4`}</strong>
              <small>Job #{rowJob.id} - {rowJob.progress_percentage}%</small>
            </span>
            <span>{video?.source_url.startsWith("file://") ? "Local MP4" : "Douyin"}</span>
            <span className={rowJob.status === "failed" || rowJob.status === "canceled" ? "badStatus" : "goodStatus"}>{rowJob.status}</span>
            <span className="tableActions">
              <button onClick={() => window.open(api.renderDownloadUrl(rowJob.id), "_blank")} disabled={rowJob.status !== "completed" || !rowJob.output_video_path} type="button">Download</button>
              <button className="dangerAction" onClick={() => cancelRender(rowJob.id)} disabled={rowJob.status === "completed"} type="button">Cancel</button>
              <button onClick={() => loadCaption(true)} disabled={!activeVideo} type="button">Caption</button>
              <button onClick={shareCurrent} disabled={!activeVideo} type="button">Share</button>
            </span>
          </div>
        ))}
        {renderRows.length === 0 && <p className="emptyState inline">No matching render history.</p>}
      </div>

      {latestJob && (
        <div className="jobStrip">
          <strong>Job #{latestJob.id}: {latestJob.status} - {latestJob.progress_percentage}%</strong>
          <div className="progress"><span style={{ width: `${latestJob.progress_percentage}%` }} /></div>
          {latestJob.error_message && <small>{latestJob.error_message}</small>}
          {latestJob.status === "completed" && <a href={api.renderDownloadUrl(latestJob.id)}>Download MP4</a>}
        </div>
      )}

      <div className="exportActions">
        <button className="lineBtn" onClick={() => loadCaption(true)} disabled={!activeVideo} type="button">Copy caption</button>
        <button className="lineBtn" onClick={cleanupFiles} disabled={!activeVideo} type="button">Cleanup storage</button>
        <button className="renderBtn" onClick={startRender} disabled={!activeVideo || busy} type="button">Render selected</button>
      </div>
      {caption && <textarea className="captionPreview" readOnly value={caption} />}
    </section>
  );
}

function RenderQueueCard({
  name,
  progress,
  eta,
  job,
  cancelRender,
}: {
  name: string;
  progress: number;
  eta: string;
  job: RenderJob | null;
  cancelRender: (jobId: number) => Promise<void>;
}) {
  const canCancel = Boolean(job && (job.status === "queued" || job.status === "rendering"));
  return (
    <article className="queueCard">
      <div className="queueIcon">R</div>
      <div>
        <div className="queueTitle">
          <strong>{name}</strong>
          <span>{progress}%</span>
        </div>
        <small>1080p - 60fps - H.264</small>
        <div className="progress"><span style={{ width: `${progress}%` }} /></div>
        <div className="queueFoot">
          <span>{eta}</span>
          <button type="button" disabled={!canCancel} onClick={() => job && cancelRender(job.id)}>
            {job?.status === "cancel_requested" ? "Canceling" : "Cancel"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

function formatTime(value: number) {
  const minutes = Math.floor(value / 60).toString().padStart(2, "0");
  const seconds = Math.floor(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function updateSegment(
  index: number,
  key: "text_vi" | "text_vi_optimized",
  value: string,
  segments: Segment[],
  setSegments: React.Dispatch<React.SetStateAction<Segment[]>>
) {
  const next = [...segments];
  next[index] = { ...next[index], [key]: value };
  setSegments(next);
}

createRoot(document.getElementById("root")!).render(<App />);
