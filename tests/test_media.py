import hashlib
import subprocess
import wave
from dataclasses import replace
from unittest.mock import Mock

import pytest

from bili_notes.core import CancelToken, Cancelled, Settings, TaskError
from bili_notes.media import Media


def test_real_ffmpeg_audio_split_preserves_source(tmp_path):
    source = tmp_path / "测试 {音频}.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 16000 * 3)
    digest = hashlib.sha256(source.read_bytes()).digest()
    job = tmp_path / "job"
    job.mkdir()
    media = Media(replace(Settings(), chunk_seconds=1), CancelToken(), lambda *args: None)
    chunks = media.split(source, job)
    assert len(chunks) >= 3
    assert all(p.stat().st_size > 0 for p in chunks)
    assert hashlib.sha256(source.read_bytes()).digest() == digest


def test_ffmpeg_is_killed_before_cancellation_cleanup(tmp_path, monkeypatch):
    token = CancelToken()
    media = Media(Settings(), token, lambda *args: None)
    monkeypatch.setattr(media, "ffmpeg", lambda: "ffmpeg")
    process = Mock()
    process.poll.return_value = None

    def start(*args, **kwargs):
        token.cancel()
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    with pytest.raises(Cancelled):
        media.split(tmp_path / "source.wav", tmp_path)
    process.kill.assert_called_once()
    process.wait.assert_called_once()


def test_cookie_file_is_copied_not_modified(tmp_path):
    source = tmp_path / "private.txt"
    source.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    job = tmp_path / "job"
    job.mkdir()
    media = Media(Settings(cookies=str(source)), CancelToken(), lambda *args: None)
    options = media.options(job)
    assert options["cookiefile"] != str(source)
    assert source.read_text() == "# Netscape HTTP Cookie File\n"


def test_real_ytdlp_subtitle_writer_with_embedded_subtitle(tmp_path, monkeypatch):
    import yt_dlp

    info = {
        "id": "fixture",
        "title": "字幕样例",
        "ext": "mp4",
        "format_id": "test",
        "url": "https://example.invalid/media",
        "subtitles": {
            "zh-CN": [{"ext": "srt", "data": "1\n00:00:01,000 --> 00:00:02,000\n字幕事实\n"}]
        },
    }

    def extract(ydl, *args, **kwargs):
        # Reproduce yt-dlp's real extractor gate; without flags, subtitles are omitted.
        return info if ydl.params.get("writesubtitles") else {**info, "subtitles": {}}

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", extract)
    media = Media(Settings(), CancelToken(), lambda *args: None)
    title, subtitle = media.resolve("https://www.bilibili.com/video/BV1xx411c7mD", tmp_path)
    assert title == "字幕样例"
    assert subtitle == "[00:00:01] 字幕事实"
    assert not list(tmp_path.glob("*.mp4"))


def test_download_uses_returned_filepath_not_newest_mp3(tmp_path, monkeypatch):
    import yt_dlp

    downloaded = tmp_path / "source.m4a"
    downloaded.write_bytes(b"right audio")
    unrelated = tmp_path / "newest.mp3"
    unrelated.write_bytes(b"wrong audio")
    info = {
        "id": "test",
        "title": "测试",
        "ext": "m4a",
        "requested_downloads": [{"filepath": str(downloaded)}],
    }
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", lambda *args, **kwargs: info)
    media = Media(Settings(), CancelToken(), lambda *args: None)
    assert media.download("https://www.bilibili.com/video/BV1xx411c7mD", tmp_path) == downloaded


def test_subtitle_discovery_failure_retries_without_subtitle_flags(tmp_path, monkeypatch):
    import yt_dlp

    calls = []

    def extract(ydl, *args, **kwargs):
        calls.append(ydl.params.get("writesubtitles"))
        if calls[-1]:
            raise yt_dlp.utils.DownloadError("subtitle service unavailable")
        return {"id": "test", "title": "仍可下载的视频"}

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", extract)
    media = Media(Settings(), CancelToken(), lambda *args: None)
    assert media.resolve("https://www.bilibili.com/video/BV1xx411c7mD", tmp_path) == (
        "仍可下载的视频",
        None,
    )
    assert calls == [True, False]


def test_bilibili_412_is_reported_without_repeated_requests(tmp_path, monkeypatch):
    import yt_dlp

    extract = Mock(side_effect=yt_dlp.utils.DownloadError("HTTP Error 412: Precondition Failed"))
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", extract)
    media = Media(Settings(), CancelToken(), lambda *args: None)
    with pytest.raises(TaskError, match="HTTP 412"):
        media.resolve("https://www.bilibili.com/video/BV1xx411c7mD", tmp_path)
    extract.assert_called_once()
