from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./tool_tiktok.db"
    storage_dir: Path = Path("../storage")
    watch_dir: Path = Path("../storage/inbox")
    douyin_local_download_dir: Path = Path("../storage/inbox")
    enable_local_watcher: bool = False
    local_watcher_window_minutes: int = 10
    api_cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174"
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    fpt_ai_api_key: str | None = None
    tikhub_api_key: str | None = None
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_hot_search_path: str = "/api/v1/douyin/web/fetch_hot_search_list"
    fpt_ai_default_voice: str = "banmai"
    fpt_ai_default_speed: str = "0"
    fpt_ai_poll_attempts: int = 12
    fpt_ai_poll_interval_seconds: float = 2.0
    fpt_ai_request_timeout_seconds: float = 15.0
    elevenlabs_default_voice_id: str | None = None
    elevenlabs_voices: str = ""
    omnivoice_model: str = "k2-fsa/OmniVoice"
    omnivoice_device: str = "cuda:0"
    omnivoice_dtype: str = "float16"
    omnivoice_voices: str = ""
    asr_provider: str = "local"
    local_whisper_model: str = "small"
    openai_asr_model: str = "whisper-1"
    openai_translation_model: str = "gpt-4o-mini"
    translation_batch_size: int = 16
    translation_glossary: str = (
        "Douyin=Douyin; TikTok Trung Quoc=Douyin; 宝子们=cac ban oi; "
        "带货=ban hang/chot don tuy ngu canh"
    )
    tts_parallel_workers: int = 6
    douyin_cookies_path: str = "/storage/cookies/douyin_cookies.txt"
    tiktok_cookies_path: str = "./cookies.json"

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.watch_dir.mkdir(parents=True, exist_ok=True)
    settings.douyin_local_download_dir.mkdir(parents=True, exist_ok=True)
    return settings
