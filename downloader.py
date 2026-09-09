from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[int, str], None]
LogCallback = Callable[[str], None]


class MediaError(RuntimeError):
    pass


class YTDLPLogger:
    def __init__(self, callback: LogCallback):
        self.callback = callback

    def _write(self, level: str, message: str) -> None:
        if message:
            self.callback(f"[{level}] {message}")

    def debug(self, message: str) -> None:
        self._write("debug", message)

    def info(self, message: str) -> None:
        self._write("info", message)

    def warning(self, message: str) -> None:
        self._write("warning", message)

    def error(self, message: str) -> None:
        self._write("error", message)


def find_ffmpeg() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise MediaError(
            "没有找到 FFmpeg。请安装 imageio-ffmpeg，或把 ffmpeg 加入 PATH。"
        ) from exc


def normalize_audio(
    source: str | Path,
    output_dir: str | Path,
    progress: ProgressCallback,
    log: LogCallback,
) -> Path:
    """Convert any supported local media to a small mono MP3 for Gemini."""
    source = Path(source).expanduser().resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source.is_file():
        raise MediaError(f"文件不存在：{source}")

    target = output_dir / "audio_for_gemini.mp3"
    ffmpeg = find_ffmpeg()
    progress(38, "正在转换音频…")

    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "64k",
        str(target),
    ]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if result.returncode != 0:
        log(result.stderr.strip())
        raise MediaError("FFmpeg 转换失败。请确认文件包含可读取的音轨。")

    if not target.is_file() or target.stat().st_size == 0:
        raise MediaError("FFmpeg 没有生成有效的 MP3 文件。")

    progress(48, "音频准备完成")
    return target


def download_bilibili_audio(
    url: str,
    output_dir: str | Path,
    cookie_file: str,
    progress: ProgressCallback,
    log: LogCallback,
    keep_dir: str | Path | None = None,
) -> Path:
    """
    One yt-dlp extraction pass only.

    No subtitle preflight, no hand-written Bilibili API calls, no custom WBI logic.
    """
    import yt_dlp

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    def hook(data: dict) -> None:
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes", 0)
            if total:
                pct = max(0, min(100, int(downloaded * 100 / total)))
                progress(8 + pct // 4, f"正在下载音频：{pct}%")
            else:
                progress(12, "正在下载音频…")
        elif data.get("status") == "finished":
            progress(34, "下载完成，正在准备音频…")

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "verbose": True,
        "no_color": True,
        "logger": YTDLPLogger(log),
        "progress_hooks": [hook],
        "socket_timeout": 30,
        "retries": 1,
        "fragment_retries": 2,
    }

    if cookie_file:
        original_cookie = Path(cookie_file).expanduser().resolve()
        if not original_cookie.is_file():
            raise MediaError("设置的 Cookie 文件不存在，请重新选择。")
        # yt-dlp may update a cookie file; never let it write into the user's original.
        temp_cookie = output_dir / "cookies.txt"
        shutil.copy2(original_cookie, temp_cookie)
        options["cookiefile"] = str(temp_cookie)

    progress(5, "正在连接 B 站并解析音频…")
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise MediaError("yt-dlp 没有返回视频信息。")
            if info.get("_type") in {"playlist", "multi_video"}:
                raise MediaError("当前只处理单个视频，请不要输入合集/播放列表链接。")
    except MediaError:
        raise
    except Exception as exc:
        text = str(exc)
        log(f"[exception] {text}")
        if "412" in text or "request was banned" in text.lower():
            raise MediaError(
                "B 站返回 412 / request was banned。\n"
                "这通常发生在 yt-dlp 与 B 站访问策略这一层，不是 Gemini 错误。\n"
                "可先更新 yt-dlp；若该视频需要登录，再在设置中选择你自己的 Cookie 文件；"
                "仍失败时请稍后再试，或改用本地音频。"
            ) from exc
        raise MediaError(f"B 站音频下载失败：{text}") from exc

    candidates = [
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name != "cookies.txt"
        and path.suffix.lower() not in {".part", ".ytdl", ".json"}
    ]
    if not candidates:
        raise MediaError("下载结束，但没有找到音频文件。请查看下载日志。")

    # With outtmpl=source.%(ext)s there should normally be one file.
    source = max(candidates, key=lambda p: p.stat().st_size)

    if keep_dir is not None:
        keep_dir = Path(keep_dir).expanduser().resolve()
        keep_dir.mkdir(parents=True, exist_ok=True)
        try:
            from yt_dlp.utils import sanitize_filename

            title = sanitize_filename(str(info.get("title") or "B站音频"), restricted=False)
        except Exception:
            title = str(info.get("title") or "B站音频")
            for ch in '<>:"/\\|?*':
                title = title.replace(ch, "_")

        video_id = str(info.get("id") or "").strip()
        stem = f"{title} [{video_id}]" if video_id else title
        target = keep_dir / f"{stem}{source.suffix.lower()}"

        # Avoid overwriting a previous download with the same title.
        if target.exists():
            index = 2
            while True:
                candidate = keep_dir / f"{stem} ({index}){source.suffix.lower()}"
                if not candidate.exists():
                    target = candidate
                    break
                index += 1

        shutil.copy2(source, target)
        log(f"[saved] 已保留下载音频：{target}")
        progress(36, f"已保留下载音频：{target.name}")

    return source
