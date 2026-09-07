from pathlib import Path

import pytest

from bili_notes.core import CancelToken, Cancelled, Request, Settings, Store, TaskError
from bili_notes.pipeline import Pipeline


class AI:
    instances = []
    fail = False

    def __init__(self, *args):
        self.calls = []
        self.closed = False
        self.api_calls = self.cached_calls = self.prompt_tokens = self.output_tokens = 0
        self.instances.append(self)

    def generate(self, prompt, text="", audio=None):
        if self.fail:
            raise TaskError("simulated failure")
        self.calls.append((prompt, text, audio))
        self.api_calls += 1
        return "[00:00:01] 测试素材中的事实与结论。"

    def close(self):
        self.closed = True


class Media:
    subtitle = "[00:00:01] 从字幕提取的内容"
    downloaded = False
    resolved = False

    def __init__(self, *args):
        pass

    def resolve(self, url, directory, subtitles=True):
        type(self).resolved = True
        return "测试视频", self.subtitle if subtitles else None

    def download(self, url, directory):
        type(self).downloaded = True
        path = directory / "source.webm"
        path.write_bytes(b"downloaded")
        return path

    def split(self, source, directory):
        assert Path(source).is_file()
        files = [directory / f"{i}.mp3" for i in range(2)]
        for path in files:
            path.write_bytes(b"audio")
        return files


@pytest.fixture
def setup(tmp_path):
    AI.instances.clear()
    AI.fail = False
    Media.subtitle = "[00:00:01] 从字幕提取的内容"
    Media.downloaded = False
    Media.resolved = False
    store = Store(tmp_path / "data")
    token = CancelToken()
    pipeline = Pipeline(store, Settings(), token, lambda *args: None, AI, Media)
    return pipeline, store, token


def test_subtitle_priority_skips_download(setup):
    pipeline, store, _ = setup
    result = pipeline.run(Request("BV1xx411c7mD"), "fake")
    assert result.input_kind == "视频字幕"
    assert not Media.downloaded
    assert result.transcript
    assert len(store.history()) == 1
    assert not list((store.root / "temp").iterdir())
    assert AI.instances[-1].closed


def test_audio_fallback_does_not_claim_to_be_transcript(setup):
    pipeline, store, _ = setup
    Media.subtitle = None
    result = pipeline.run(Request("BV1xx411c7mD"), "fake")
    assert Media.downloaded
    assert result.transcript == ""
    calls = AI.instances[-1].calls
    assert "00:08:00" in calls[1][0]
    assert len(calls) == 3


def test_direct_audio_mode_skips_subtitle_preflight(setup):
    pipeline, _, _ = setup
    pipeline.run(Request("BV1xx411c7mD", "audio"), "fake")
    assert Media.downloaded
    assert not Media.resolved


def test_local_transcription_and_failure_never_modify_original(setup, tmp_path):
    pipeline, store, _ = setup
    source = tmp_path / "中文 {素材}.wav"
    source.write_bytes(b"original")
    result = pipeline.run(Request(str(source), "transcript"), "fake")
    assert result.transcript
    assert "逐句完整转写" in AI.instances[-1].calls[0][0]
    AI.fail = True
    with pytest.raises(TaskError):
        pipeline.run(Request(str(source)), "fake")
    assert source.read_bytes() == b"original"
    assert not list((store.root / "temp").iterdir())
    assert len(store.history()) == 1
    assert AI.instances[-1].closed


def test_cancelled_job_does_not_create_history(setup):
    pipeline, store, token = setup
    token.cancel()
    with pytest.raises(Cancelled):
        pipeline.run(Request("BV1xx411c7mD"), "fake")
    assert store.history() == []


def test_long_text_uses_multiple_map_calls_then_final_summary(setup, tmp_path):
    pipeline, _, _ = setup
    source = tmp_path / "transcript.txt"
    source.write_text("这是很长的逐字稿。\n" * 7000, encoding="utf-8")
    result = pipeline.run(Request(str(source)), "fake")
    assert len(result.transcript) > 60000
    assert len(AI.instances[-1].calls) > 4


def test_empty_transcript_is_not_success(setup, tmp_path):
    pipeline, store, _ = setup
    source = tmp_path / "empty.txt"
    source.write_text("")
    with pytest.raises(TaskError):
        pipeline.run(Request(str(source)), "fake")
    assert not store.history()
