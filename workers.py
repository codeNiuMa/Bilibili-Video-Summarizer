from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from downloader import MediaError, download_bilibili_audio, normalize_audio
from gemini_summarizer import GeminiError, summarize_audio
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
            api_key: str,
            model: str,
            cookie_file: str,
            keep_download: bool,
            latest_log: Path,
            parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.local_file = local_file
        self.api_key = api_key
        self.model = model
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
                    audio = normalize_audio(
                        self.local_file,
                        temp_dir / "prepared",
                        self._progress,
                        self._write_log,
                    )

                # Extra UI metadata only; does not alter the stable processing flow.
                try:
                    source_path = Path(source) if self.url else Path(self.local_file)
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
                    # UI metadata must never affect summarization.
                    pass

                result = summarize_audio(
                    audio_path=audio,
                    api_key=self.api_key,
                    model=self.model,
                    progress=self._progress,
                )

            self.result_ready.emit(result)
        except (MediaError, GeminiError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self._write_log(f"[unexpected] {type(exc).__name__}: {exc}")
            self.failed.emit(f"未预期错误：{exc}")


class ModelRefreshThread(QThread):
    models_ready = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key

    def run(self) -> None:
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key.strip())
            names: list[str] = []

            for model in client.models.list():
                name = str(getattr(model, "name", "") or "").strip()
                actions = getattr(model, "supported_actions", None) or []
                actions_normalized = {
                    str(action).replace("_", "").lower() for action in actions
                }
                if "generatecontent" not in actions_normalized:
                    continue
                if name.startswith("models/"):
                    name = name[7:]
                if name.startswith("gemini-"):
                    names.append(name)

            names = sorted(set(names))
            if not names:
                raise RuntimeError("当前 API Key 没有查询到可用于 generateContent 的 Gemini 模型。")
            self.models_ready.emit(names)
        except Exception as exc:
            self.failed.emit(str(exc))
