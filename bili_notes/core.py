from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

DEFAULT_MODEL = "gemini-3.1-flash-lite"
MEDIA_EXTENSIONS = {
    ".m4s",
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".aac",
    ".flac",
    ".ogg",
    ".webm",
    ".mkv",
    ".mov",
}
TEXT_EXTENSIONS = {".txt", ".srt", ".vtt", ".json", ".json3"}
STYLES = {"concise": "精简速览", "detailed": "详细笔记", "action": "行动清单"}
MODES = {
    "auto": "智能模式 · 字幕优先",
    "audio": "直接听音频 · 快速总结",
    "transcript": "完整转写 · 再总结",
}


class Cancelled(Exception):
    pass


class TaskError(Exception):
    pass


class CancelToken:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise Cancelled("任务已取消；已完成片段可在下次运行时复用。")

    def wait(self, seconds):
        if self.event.wait(seconds):
            self.check()


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    cookies: str = ""
    ffmpeg: str = ""
    chunk_seconds: int = 480


@dataclass(frozen=True)
class Request:
    source: str
    mode: str = "auto"
    style: str = "detailed"


@dataclass
class Result:
    id: str
    title: str
    source: str
    model: str
    mode: str
    created: str
    summary: str
    transcript: str
    input_kind: str
    cached_calls: int = 0
    api_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0

    def markdown(self):
        title = html.escape(self.title).replace("\n", " ")
        source = html.escape(self.source).replace("`", "'").replace("\n", " ")
        return (
            f"# {title}\n\n> {self.created} · {self.model} · {self.input_kind}\n\n"
            f"来源：`{source}`\n\n{self.summary}\n"
        )


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(
            os.environ.get("BILI_NOTES_DATA", Path(__file__).resolve().parents[1] / "data")
        )
        self.root = self.root.resolve()
        for name in ("history", "cache", "temp"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def settings(self):
        try:
            data = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
            value = Settings(
                **{k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
            )
            if not isinstance(value.model, str) or not value.model.strip():
                return Settings()
            if not isinstance(value.chunk_seconds, int) or not 60 <= value.chunk_seconds <= 900:
                return Settings()
            if not all(isinstance(x, str) for x in (value.cookies, value.ffmpeg)):
                return Settings()
            return value
        except (OSError, ValueError, TypeError, AttributeError):
            return Settings()

    def save_settings(self, value: Settings):
        atomic_json(self.root / "settings.json", asdict(value))

    def save(self, result: Result):
        atomic_json(self.root / "history" / f"{result.id}.json", asdict(result))

    def history(self):
        results = []
        for path in (self.root / "history").glob("*.json"):
            try:
                result = Result(**json.loads(path.read_text(encoding="utf-8")))
                if not all(
                    isinstance(getattr(result, name), str)
                    for name in (
                        "id",
                        "title",
                        "source",
                        "model",
                        "mode",
                        "created",
                        "summary",
                        "transcript",
                        "input_kind",
                    )
                ):
                    continue
                if not all(
                    isinstance(getattr(result, name), int)
                    for name in ("cached_calls", "api_calls", "prompt_tokens", "output_tokens")
                ):
                    continue
                results.append(result)
            except (OSError, ValueError, TypeError):
                continue
        return sorted(results, key=lambda r: r.created, reverse=True)

    def cache_get(self, key):
        try:
            value = json.loads((self.root / "cache" / f"{key}.json").read_text(encoding="utf-8"))
            return value if isinstance(value, str) and value.strip() else None
        except (OSError, ValueError):
            return None

    def cache_put(self, key, text):
        atomic_json(self.root / "cache" / f"{key}.json", text)

    def clear_cache(self):
        # Non-recursive: never touch user media or active temporary jobs.
        for path in (self.root / "cache").glob("*.json"):
            if path.is_file() and not path.is_symlink():
                path.unlink()


def cache_key(*values):
    return hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def normalize_url(value: str):
    value = value.strip()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", value):
        return f"https://www.bilibili.com/video/{value}"
    match = re.search(r"https?://[^\s<>]+", value)
    if not match:
        raise TaskError("请输入 B 站视频链接、b23.tv 短链接或 BV 号。")
    try:
        url = urlsplit(match.group(0).rstrip("，。；）)】]"))
        port = url.port
    except ValueError as exc:
        raise TaskError("视频链接地址格式不正确。") from exc
    if url.username or url.password or port not in (None, 80, 443):
        raise TaskError("视频链接包含不支持的地址信息。")
    host = (url.hostname or "").lower()
    if host not in {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"}:
        raise TaskError("当前仅支持 bilibili.com 视频链接和 b23.tv 短链接。")
    if host != "b23.tv" and not re.match(r"^/video/(BV[0-9A-Za-z]{10}|av\d+)(?:/|$)", url.path):
        raise TaskError("请使用 /video/BV… 视频页面，暂不支持合集、直播或个人空间。")
    query = parse_qs(url.query)
    page = query.get("p", ["1"])[0]
    if not page.isdigit() or int(page) < 1:
        raise TaskError("分 P 编号必须为正整数。")
    return urlunsplit(("https", host, url.path, urlencode({"p": page}) if "p" in query else "", ""))


def timestamp(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def parse_subtitle(text: str, suffix: str):
    if suffix.lower() in {".json", ".json3"}:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise TaskError("字幕 JSON 格式损坏，请重新导出字幕文件。") from exc
        if isinstance(data, dict) and "body" in data:
            return "\n".join(
                f"[{timestamp(x.get('from', 0))}] {x.get('content', '')}"
                for x in data["body"]
                if x.get("content")
            )
        if isinstance(data, dict) and "events" in data:
            return "\n".join(
                f"[{timestamp(x.get('tStartMs', 0) / 1000)}] "
                + "".join(s.get("utf8", "") for s in x.get("segs", []))
                for x in data["events"]
                if x.get("segs")
            )
        raise TaskError("无法识别字幕 JSON；支持 B 站 body 和 JSON3 events 格式。")
    if suffix.lower() == ".txt":
        return text.strip()
    lines, last = [], ""
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        rows = block.strip().splitlines()
        timing = next((i for i, line in enumerate(rows) if "-->" in line), None)
        if timing is None:
            continue
        start = rows[timing].split("-->")[0].strip().replace(",", ".").split(".")[0]
        content = html.unescape(re.sub(r"<[^>]*>", "", " ".join(rows[timing + 1 :]))).strip()
        if content and content != last:
            lines.append(f"[{start}] {content}")
            last = content
    return "\n".join(lines)


def split_text(text: str, limit=18000):
    if limit < 1:
        raise ValueError("limit must be positive")
    chunks = []
    while len(text) > limit:
        end = text.rfind("\n", limit // 2, limit)
        end = end + 1 if end >= 0 else limit
        chunks.append(text[:end])
        text = text[end:]
    if text:
        chunks.append(text)
    return chunks


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")
