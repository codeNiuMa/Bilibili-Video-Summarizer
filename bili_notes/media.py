from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .core import Cancelled, TaskError


def is_bili_gate(exc):
    return "HTTP Error 412" in str(exc)


def download_error(exc, fallback):
    if is_bili_gate(exc):
        return "B 站暂时拒绝下载请求（HTTP 412）。请稍后重试或使用已下载的本地文件。"
    return fallback


class QuietLogger:
    # yt-dlp exceptions can contain signed URLs/cookies; UI gets controlled messages.
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


class Media:
    def __init__(self, settings, token, progress):
        self.settings, self.token, self.progress = settings, token, progress

    def options(self, directory):
        def hook(data):
            self.token.check()
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                percent = int(data.get("downloaded_bytes", 0) * 100 / total) if total else 0
                self.progress(
                    "下载音频",
                    12 + min(percent, 100) // 5,
                    f"已下载 {percent}%" if total else "正在下载音频…",
                )

        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(directory / "source.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "progress_hooks": [hook],
        }
        if self.settings.cookies:
            source = Path(self.settings.cookies).expanduser().resolve()
            if not source.is_file():
                raise TaskError("Cookie 文件不存在，请在设置中重新选择。")
            # yt-dlp may save cookies on exit; operate on an owned copy only.
            copy = directory / "cookies.txt"
            if not copy.exists():
                shutil.copyfile(source, copy)
            opts["cookiefile"] = str(copy)
        return opts

    def download(self, url, directory):
        import yt_dlp

        self.token.check()
        self.progress("下载音频", 5, "正在按旧版流程解析并下载音频…")
        try:
            with yt_dlp.YoutubeDL(self.options(directory)) as ydl:
                info = ydl.extract_info(url, download=True)
                self.token.check()
                if not info or info.get("_type") in {"playlist", "multi_video"}:
                    raise TaskError("不支持批量合集下载，请使用单视频链接。")
                candidates = [x.get("filepath") for x in info.get("requested_downloads", [])]
                candidates.append(ydl.prepare_filename(info))
                for value in candidates:
                    if value:
                        path = Path(value).resolve()
                        if path.is_file() and path.is_relative_to(directory.resolve()):
                            return path
                raise TaskError("下载器没有返回有效音频路径，请更新 yt-dlp。")
        except (Cancelled, TaskError):
            raise
        except Exception as exc:
            self.token.check()
            raise TaskError(
                download_error(
                    exc, "音频下载失败。请检查网络和视频权限；可稍后重试或改用本地文件。"
                )
            ) from exc

    def ffmpeg(self):
        if self.settings.ffmpeg:
            path = Path(self.settings.ffmpeg).expanduser()
            if not path.is_file():
                raise TaskError("设置中的 FFmpeg 路径不存在。")
            return str(path.resolve())
        if system := shutil.which("ffmpeg"):
            return system
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise TaskError(
                "未找到 FFmpeg。请安装 imageio-ffmpeg 或在设置中指定 ffmpeg.exe。"
            ) from exc

    def split(self, source, directory):
        self.token.check()
        self.progress("准备音频", 35, "正在转换为单声道语音，并按片段切分…")
        chunk_dir = directory / "chunks"
        chunk_dir.mkdir()
        command = [
            self.ffmpeg(),
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
            "48k",
            "-f",
            "segment",
            "-segment_time",
            str(self.settings.chunk_seconds),
            "-reset_timestamps",
            "1",
            str(chunk_dir / "%05d.mp3"),
        ]
        # File-backed stderr avoids pipe deadlocks; killed/waited before temp cleanup.
        with (directory / "ffmpeg.log").open("wb") as error_file:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=error_file,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                while process.poll() is None:
                    self.token.wait(0.15)
                self.token.check()
                if process.returncode:
                    raise TaskError("音频转换失败。文件可能损坏或没有音轨；B 站缓存请选音频 m4s。")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        chunks = sorted(chunk_dir.glob("*.mp3"))
        if not chunks:
            raise TaskError("没有提取到音频片段。")
        return chunks
