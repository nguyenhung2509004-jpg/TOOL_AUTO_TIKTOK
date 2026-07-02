export type SourceVideo = {
  id: number;
  source_url: string;
  caption_original: string | null;
  raw_video_path: string | null;
  duration: number | null;
  status: string;
  error_message: string | null;
};

export type Segment = {
  id: number;
  start_time: number;
  end_time: number;
  text_cn: string;
  text_vi: string | null;
  text_vi_optimized: string | null;
  voice_duration: number | null;
  max_duration: number;
  warning: boolean;
};

export type RenderJob = {
  id: number;
  video_id: number;
  status: string;
  progress_percentage: number;
  output_video_path: string | null;
  error_message: string | null;
  created_at?: string;
  completed_at?: string | null;
};

export type Caption = {
  caption: string;
  hashtags: string[];
};

export type TTSVoice = {
  id: string;
  label: string;
  provider: string;
  voice_id: string;
};

export type Niche = {
  label_vi: string;
  keyword_cn: string;
};

export type DouyinTrend = {
  id: number;
  video_id: string | null;
  source_url: string;
  author_name: string | null;
  author_id: string | null;
  caption: string | null;
  cover_url: string | null;
  like_count: number;
  comment_count: number;
  share_count: number;
  collect_count: number;
  duration: number | null;
  create_time: number | null;
  hot_score: number;
  niche: string | null;
  status: string;
  waiting_download: boolean;
  waiting_since: string | null;
  raw_video_path: string | null;
  imported_file_name: string | null;
  created_at: string;
  updated_at: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  importDouyin(url: string) {
    return request<{ video_id: number; status: string; task_id: string; message: string }>("/api/douyin/import", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  },
  scanLocal() {
    return request<{ imported: Array<{ video_id: number; status: string; task_id: string; message: string }>; skipped: string[]; watch_dir: string }>("/api/local/scan", {
      method: "POST",
    });
  },
  uploadLocal(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<{ video_id: number; status: string; task_id: string; message: string }>("/api/local/upload", {
      method: "POST",
      body,
    });
  },
  reimport(videoId: number) {
    return request<{ video_id: number; status: string; task_id: string; message: string }>(`/api/videos/${videoId}/reimport`, {
      method: "POST",
    });
  },
  videos() {
    return request<SourceVideo[]>("/api/videos");
  },
  video(id: number) {
    return request<SourceVideo>(`/api/videos/${id}`);
  },
  updateVideo(videoId: number, payload: { source_url?: string; caption_original?: string }) {
    return request<SourceVideo>(`/api/videos/${videoId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  deleteVideo(videoId: number) {
    return request<{ video_id: number; deleted_files: number; message: string }>(`/api/videos/${videoId}`, {
      method: "DELETE",
    });
  },
  segments(videoId: number) {
    return request<Segment[]>(`/api/videos/${videoId}/segments`);
  },
  updateSegments(videoId: number, segments: Segment[]) {
    return request<Segment[]>(`/api/videos/${videoId}/segments`, {
      method: "PUT",
      body: JSON.stringify({
        segments: segments.map((segment) => ({
          id: segment.id,
          text_vi: segment.text_vi,
          text_vi_optimized: segment.text_vi_optimized,
        })),
      }),
    });
  },
  render(
    videoId: number,
    originalAudioVolume: number,
    burnSubtitles: boolean,
    options?: { ttsProvider?: string; voiceId?: string; voiceVolume?: number }
  ) {
    return request<RenderJob>(`/api/videos/${videoId}/render`, {
      method: "POST",
      body: JSON.stringify({
        tts_provider: options?.ttsProvider ?? "local",
        voice_id: options?.voiceId ?? "vi_default",
        original_audio_volume: originalAudioVolume,
        voice_volume: options?.voiceVolume ?? 1,
        burn_subtitles: burnSubtitles,
      }),
    });
  },
  rawVideoUrl(videoId: number) {
    return `${API_BASE}/api/videos/${videoId}/raw`;
  },
  renderJobs(params?: { videoId?: number }) {
    const search = new URLSearchParams();
    if (params?.videoId) search.set("video_id", String(params.videoId));
    const suffix = search.toString() ? `?${search}` : "";
    return request<RenderJob[]>(`/api/render-jobs${suffix}`);
  },
  renderJob(jobId: number) {
    return request<RenderJob>(`/api/render-jobs/${jobId}`);
  },
  cancelRenderJob(jobId: number) {
    return request<{ job_id: number; deleted: boolean; message: string }>(`/api/render-jobs/${jobId}/cancel`, { method: "POST" });
  },
  renderDownloadUrl(jobId: number) {
    return `${API_BASE}/api/render-jobs/${jobId}/download`;
  },
  caption(videoId: number) {
    return request<Caption>(`/api/videos/${videoId}/caption`);
  },
  cleanup(videoId: number) {
    return request<{ video_id: number; deleted_files: number; kept_files: number }>(`/api/videos/${videoId}/cleanup`, {
      method: "POST",
    });
  },
  ttsVoices() {
    return request<TTSVoice[]>("/api/tts/voices");
  },
  niches() {
    return request<Niche[]>("/api/douyin/trends/niches");
  },
  trends(params?: { status?: string; niche?: string }) {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.niche) search.set("niche", params.niche);
    const suffix = search.toString() ? `?${search}` : "";
    return request<DouyinTrend[]>(`/api/douyin/trends${suffix}`);
  },
  scanTrends(niche: string, limit = 20) {
    return request<DouyinTrend[]>("/api/douyin/trends/scan", {
      method: "POST",
      body: JSON.stringify({ niche, limit }),
    });
  },
  waitTrend(trendId: number) {
    return request<DouyinTrend>(`/api/douyin/trends/${trendId}/waiting-download`, { method: "POST" });
  },
  cancelWaitTrend(trendId: number) {
    return request<DouyinTrend>(`/api/douyin/trends/${trendId}/cancel-waiting`, { method: "POST" });
  },
  attachTrendFile(trendId: number, filePath: string) {
    return request<{ trend: DouyinTrend; message: string }>(`/api/douyin/trends/${trendId}/attach-local-file`, {
      method: "POST",
      body: JSON.stringify({ file_path: filePath }),
    });
  },
};
