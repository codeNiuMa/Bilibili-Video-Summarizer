from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ai.base import ProviderError
from ai.manager import list_provider_models, summarize_audio_with_provider
from downloader import MediaError, download_bilibili_audio, normalize_audio
from settings import DOWNLOAD_DIR, LOG_DIR


class ProcessingThread(QThread):
    progress_changed = Signal(int, str)
    media_info_ready = Signal(dict)
    result_ready = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        url: str,
        local_file: str,
        provider_id: str,
        api_keys: dict[str, str],
        provider_models: dict[str, str],
        transcription_provider: str,
        transcription_models: dict[str, str],
        cookie_file: str,
        keep_download: bool,
        latest_log: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.local_file = local_file
        self.provider_id = provider_id
        self.api_keys = dict(api_keys)
        self.provider_models = dict(provider_models)
        self.transcription_provider = transcription_provider
        self.transcription_models = dict(transcription_models)
        self.cookie_file = cookie_file
        self.keep_download = keep_download
        self.latest_log = latest_log

    def _progress(self, percent: int, text: str) -> None:
        self.progress_changed.emit(percent, text)

    def _write_log(self, line: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with self.latest_log.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line.rstrip() + "\n")

    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="bili_summarizer_") as temp:
                temp_dir = Path(temp)

                if self.url:
                    source = download_bilibili_audio(
                        url=self.url,
                        output_dir=temp_dir / "download",
                        cookie_file=self.cookie_file,
                        progress=self._progress,
                        log=self._write_log,
                        keep_dir=DOWNLOAD_DIR if self.keep_download else None,
                    )
                    audio = normalize_audio(
                        source,
                        temp_dir / "prepared",
                        self._progress,
                        self._write_log,
                    )
                else:
                    source = Path(self.local_file)
                    audio = normalize_audio(
                        self.local_file,
                        temp_dir / "prepared",
                        self._progress,
                        self._write_log,
                    )

                try:
                    source_path = Path(source)
                    source_size = source_path.stat().st_size if source_path.is_file() else 0
                    prepared_path = Path(audio)
                    prepared_size = prepared_path.stat().st_size if prepared_path.is_file() else 0
                    self.media_info_ready.emit(
                        {
                            "source_name": source_path.name,
                            "source_bytes": int(source_size),
                            "prepared_bytes": int(prepared_size),
                        }
                    )
                except Exception:
                    pass

                result = summarize_audio_with_provider(
                    audio_path=audio,
                    provider_id=self.provider_id,
                    api_keys=self.api_keys,
                    provider_models=self.provider_models,
                    transcription_provider=self.transcription_provider,
                    transcription_models=self.transcription_models,
                    progress=self._progress,
                )

            self.result_ready.emit(result)
        except (MediaError, ProviderError) as exc:
            self._write_log(f"[handled] {type(exc).__name__}: {exc}")
            self.failed.emit(str(exc))
        except Exception as exc:
            self._write_log(f"[unexpected] {type(exc).__name__}: {exc}")
            self.failed.emit(f"未预期错误：{exc}")


class ModelRefreshThread(QThread):
    models_ready = Signal(str, list)
    failed = Signal(str, str)

    def __init__(self, provider_id: str, api_key: str, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.api_key = api_key

    def run(self) -> None:
        try:
            names = list_provider_models(self.provider_id, self.api_key)
            self.models_ready.emit(self.provider_id, names)
        except Exception as exc:
            self.failed.emit(self.provider_id, str(exc))
