import json

import pytest

from bili_notes.core import (
    CancelToken,
    Cancelled,
    Settings,
    Store,
    TaskError,
    cache_key,
    normalize_url,
    parse_subtitle,
    split_text,
)


def test_url_normalization_preserves_page_and_drops_tracking():
    assert (
        normalize_url("【分享】 https://www.bilibili.com/video/BV1xx411c7mD/?p=2&share_source=copy")
        == "https://www.bilibili.com/video/BV1xx411c7mD/?p=2"
    )
    assert normalize_url("BV1xx411c7mD") == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert normalize_url("https://b23.tv/abc。") == "https://b23.tv/abc"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/video/BV1xx411c7mD",
        "https://bilibili.com.evil.com/video/BV1xx411c7mD",
        "https://www.bilibili.com/",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=0",
        "https://user:pass@b23.tv/abc",
        "ftp://b23.tv/abc",
    ],
)
def test_url_rejects_unsupported_sources(url):
    with pytest.raises(TaskError):
        normalize_url(url)


def test_srt_vtt_and_json_subtitles():
    srt = "1\n00:00:03,200 --> 00:00:06,000\n<b>你好</b> &amp; 世界\n\n2\n00:00:06,200 --> 00:00:08,000\n你好 & 世界\n"
    assert parse_subtitle(srt, ".srt") == "[00:00:03] 你好 & 世界"
    assert parse_subtitle("WEBVTT\n\n00:02.000 --> 00:05.000\n介绍", ".vtt") == "[00:02] 介绍"
    assert (
        parse_subtitle(json.dumps({"body": [{"from": 61, "content": "内容"}]}), ".json")
        == "[00:01:01] 内容"
    )
    assert (
        parse_subtitle(
            json.dumps({"events": [{"tStartMs": 2000, "segs": [{"utf8": "你好"}]}]}), ".json3"
        )
        == "[00:00:02] 你好"
    )


@pytest.mark.parametrize(
    "text",
    ["", "很长的中文" * 10000, ("line one\nline two\n" * 5000)],
    ids=["empty", "long-chinese", "many-lines"],
)
def test_chunking_preserves_every_character_and_bounds(text):
    chunks = split_text(text, 100)
    assert "".join(chunks) == text
    assert all(0 < len(x) <= 100 for x in chunks)


def test_store_corruption_and_cache_cleanup_are_scoped(tmp_path):
    store = Store(tmp_path / "data")
    (store.root / "settings.json").write_text('{"chunk_seconds": "oops"}')
    assert store.settings() == Settings()
    (store.root / "settings.json").write_text("[]")
    assert store.settings() == Settings()
    (store.root / "history" / "bad.json").write_text("{")
    assert store.history() == []
    key = cache_key("sample")
    store.cache_put(key, "可复用")
    assert store.cache_get(key) == "可复用"
    original = tmp_path / "original.mp3"
    original.write_bytes(b"original")
    store.clear_cache()
    assert original.read_bytes() == b"original"
    assert store.cache_get(key) is None
    assert (store.root / "history" / "bad.json").exists()


def test_cancel_interrupts_wait():
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        token.wait(100)
