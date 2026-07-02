import time
from pathlib import Path
from threading import Lock

import httpx

from app.core.config import get_settings
from app.services.media import ffprobe_duration


class TTSService:
    _omnivoice_model = None
    _omnivoice_model_key: tuple[str, str, str] | None = None
    _omnivoice_lock = Lock()

    def __init__(self, storage_dir: Path, provider: str = "fpt_ai", voice_id: str | None = None):
        self.segment_dir = storage_dir / "segments"
        self.segment_dir.mkdir(parents=True, exist_ok=True)
        self.settings = get_settings()
        self.provider = provider
        self.voice_id = voice_id

    def synthesize(self, segment_id: int, text: str, target_duration: float) -> tuple[Path | None, float, float]:
        clean_text = text.strip()
        if not clean_text:
            return None, 0, 1.0
        if self.provider == "omnivoice":
            return self._synthesize_omnivoice(segment_id, clean_text, target_duration)
        return self._synthesize_fpt(segment_id, clean_text, target_duration)

    def _synthesize_fpt(self, segment_id: int, text: str, target_duration: float) -> tuple[Path | None, float, float]:
        if not self.settings.fpt_ai_api_key:
            raise RuntimeError("FPT_AI_API_KEY is not configured for automatic Vietnamese TTS.")
        voice = self.voice_id or self.settings.fpt_ai_default_voice
        response = httpx.post(
            "https://api.fpt.ai/hmi/tts/v5",
            headers={
                "api-key": self.settings.fpt_ai_api_key,
                "voice": voice,
                "speed": self.settings.fpt_ai_default_speed,
            },
            content=text.encode("utf-8"),
            timeout=self.settings.fpt_ai_request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"FPT AI TTS failed: {response.text[:500]}")
        data = response.json()
        audio_url = data.get("async") or data.get("url") or data.get("audio")
        if not audio_url:
            raise RuntimeError(f"FPT AI TTS did not return an audio URL: {response.text[:500]}")
        output_path = self.segment_dir / f"{segment_id}.mp3"
        self._download_ready_audio(audio_url, output_path)
        duration = ffprobe_duration(output_path) or target_duration
        speed_ratio = duration / target_duration if target_duration > 0 else 1.0
        return output_path, duration, speed_ratio

    def _synthesize_omnivoice(self, segment_id: int, text: str, target_duration: float) -> tuple[Path | None, float, float]:
        voice = self._omnivoice_voice_config()
        output_path = self.segment_dir / f"{segment_id}.wav"
        model = self._load_omnivoice_model()
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("soundfile is not installed. Install OmniVoice runtime dependencies first.") from exc
        with self._omnivoice_lock:
            audio = model.generate(
                text=text,
                ref_audio=voice["ref_audio"],
                ref_text=voice["ref_text"],
            )
        if not audio:
            raise RuntimeError("OmniVoice returned no audio.")
        sf.write(str(output_path), audio[0], 24000)
        duration = ffprobe_duration(output_path) or target_duration
        speed_ratio = duration / target_duration if target_duration > 0 else 1.0
        return output_path, duration, speed_ratio

    def _load_omnivoice_model(self):
        model_key = (
            self.settings.omnivoice_model,
            self.settings.omnivoice_device,
            self.settings.omnivoice_dtype,
        )
        if self.__class__._omnivoice_model is not None and self.__class__._omnivoice_model_key == model_key:
            return self.__class__._omnivoice_model
        with self._omnivoice_lock:
            if self.__class__._omnivoice_model is not None and self.__class__._omnivoice_model_key == model_key:
                return self.__class__._omnivoice_model
            try:
                import torch
                from omnivoice import OmniVoice
            except ImportError as exc:
                raise RuntimeError(
                    "OmniVoice runtime is not installed. Install torch, soundfile, and omnivoice in the backend image."
                ) from exc
            dtype = {
                "float16": torch.float16,
                "float32": torch.float32,
                "bfloat16": torch.bfloat16,
            }.get(self.settings.omnivoice_dtype.lower(), torch.float16)
            self.__class__._omnivoice_model = OmniVoice.from_pretrained(
                self.settings.omnivoice_model,
                device_map=self.settings.omnivoice_device,
                dtype=dtype,
            )
            self.__class__._omnivoice_model_key = model_key
            return self.__class__._omnivoice_model

    def _omnivoice_voice_config(self) -> dict[str, str]:
        voice_id = self.voice_id or "voice_1"
        for index, raw_item in enumerate(self.settings.omnivoice_voices.split(";"), start=1):
            item = raw_item.strip()
            if not item:
                continue
            parts = [part.strip() for part in item.split("|")]
            if len(parts) >= 4:
                label, key, ref_audio, ref_text = parts[0], parts[1], parts[2], "|".join(parts[3:])
            elif len(parts) >= 3:
                label, ref_audio, ref_text = parts[0], parts[1], "|".join(parts[2:])
                key = f"voice_{index}"
            else:
                continue
            if key == voice_id:
                ref_path = Path(ref_audio)
                if not ref_path.exists():
                    raise RuntimeError(f"OmniVoice reference audio not found for {label}: {ref_audio}")
                if not ref_text:
                    raise RuntimeError(f"OmniVoice reference text is empty for {label}.")
                return {"label": label, "ref_audio": str(ref_path), "ref_text": ref_text}
        raise RuntimeError(
            f"OmniVoice voice '{voice_id}' is not configured. Add it to OMNIVOICE_VOICES."
        )

    def _download_ready_audio(self, url: str, output_path: Path) -> None:
        last_error = ""
        headers = {"User-Agent": "Mozilla/5.0"}
        attempts = max(int(self.settings.fpt_ai_poll_attempts), 1)
        interval = max(float(self.settings.fpt_ai_poll_interval_seconds), 0)
        timeout = max(float(self.settings.fpt_ai_request_timeout_seconds), 5)
        for attempt in range(attempts):
            if attempt:
                time.sleep(interval)
            response = httpx.get(url, headers=headers, follow_redirects=True, timeout=timeout)
            content_type = response.headers.get("content-type", "")
            content = response.content
            if response.status_code == 200 and (
                "audio" in content_type
                or content.startswith(b"ID3")
                or content[:2] == b"\xff\xfb"
                or content[:4] == b"RIFF"
                or content[:4] == b"OggS"
            ):
                output_path.write_bytes(response.content)
                return
            if "text/html" in content_type or content.lstrip().startswith(b"<html"):
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        raise RuntimeError(
            f"FPT AI TTS audio was not ready after {attempts} checks. Last response: {last_error}"
        )
