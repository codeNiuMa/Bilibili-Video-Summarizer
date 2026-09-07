from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from bili_notes.core import CancelToken, Cancelled, Store, TaskError
from bili_notes.gemini import Gemini


def fake_client(reason="STOP", text="笔记", state="ACTIVE"):
    client = Mock()
    uploaded = NS(name="files/test", state=NS(name=state))
    client.files.upload.return_value = uploaded
    client.files.get.return_value = NS(name="files/test", state=NS(name="ACTIVE"))
    client.models.generate_content.return_value = NS(
        text=text,
        candidates=[NS(finish_reason=NS(name=reason))],
        usage_metadata=NS(
            prompt_token_count=100, candidates_token_count=30, thoughts_token_count=5
        ),
    )
    return client


def make(tmp_path, client):
    token = CancelToken()
    token.wait = Mock(side_effect=lambda _: token.check())
    ai = Gemini("fake", "gemini-test", Store(tmp_path / "data"), token, Mock(), client)
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake audio")
    return ai, audio


def test_upload_poll_generate_delete_and_cache(tmp_path):
    client = fake_client(state="PROCESSING")
    ai, audio = make(tmp_path, client)
    assert ai.generate("prompt", audio=audio) == "笔记"
    client.files.get.assert_called_once()
    client.files.delete.assert_called_once()
    assert ai.generate("prompt", audio=audio) == "笔记"
    client.files.upload.assert_called_once()
    assert ai.cached_calls == 1
    assert ai.output_tokens == 35


@pytest.mark.parametrize("reason,text", [("MAX_TOKENS", "partial"), ("SAFETY", None), ("STOP", "")])
def test_incomplete_output_is_not_cached_and_cloud_file_is_deleted(tmp_path, reason, text):
    client = fake_client(reason, text)
    ai, audio = make(tmp_path, client)
    with pytest.raises(TaskError):
        ai.generate("prompt", audio=audio)
    assert not list((ai.store.root / "cache").glob("*.json"))
    client.files.delete.assert_called_once()


def test_cancel_during_upload_still_deletes_returned_cloud_file(tmp_path):
    client = fake_client()
    ai, audio = make(tmp_path, client)

    def upload(**kwargs):
        ai.token.cancel()
        return NS(name="files/test", state=NS(name="ACTIVE"))

    client.files.upload.side_effect = upload
    with pytest.raises(Cancelled):
        ai.generate("prompt", audio=audio)
    client.files.delete.assert_called_once()
    client.models.generate_content.assert_not_called()


def test_rate_limit_retries_but_auth_does_not(tmp_path):
    class APIError(Exception):
        code = 429

    client = fake_client()
    good = client.models.generate_content.return_value
    client.models.generate_content.side_effect = [APIError(), good]
    ai, _ = make(tmp_path, client)
    assert ai.generate("prompt", text="text") == "笔记"
    assert ai.api_calls == 2
    APIError.code = 403
    client.models.generate_content.side_effect = APIError()
    with pytest.raises(TaskError, match="访问被拒绝"):
        ai.generate("different prompt", text="text")
    assert ai.api_calls == 3


def test_cleanup_failure_is_visible_without_losing_result(tmp_path):
    client = fake_client()
    client.files.delete.side_effect = OSError()
    ai, audio = make(tmp_path, client)
    assert ai.generate("prompt", audio=audio) == "笔记"
    assert "清理提醒" in ai.progress.call_args.args[0]


def test_official_sdk_http_serialization_and_retry(tmp_path):
    import json
    import httpx
    from google import genai

    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                json={
                    "error": {
                        "code": 429,
                        "message": "rate limited",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "完成的笔记"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4},
            },
        )

    client = genai.Client(
        api_key="test-only-key",
        http_options={
            "httpx_client": httpx.Client(transport=httpx.MockTransport(handle)),
            "retry_options": {"attempts": 1},
        },
    )
    ai, _ = make(tmp_path, client)
    try:
        assert ai.generate("总结资料", text="原文内容") == "完成的笔记"
        assert ai.api_calls == 2
        body = json.loads(requests[-1].content)
        assert "systemInstruction" in body
        assert body["generationConfig"]["maxOutputTokens"] == 12000
        assert requests[-1].url.path.endswith("/models/gemini-test:generateContent")
    finally:
        ai.close()
