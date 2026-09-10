from __future__ import annotations

from pathlib import Path

from .base import AIProvider, ProgressCallback, ProviderError
from .catalog import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    provider_default_model,
    provider_display_name,
    provider_fallback_models,
)


def create_provider(provider_id: str, api_key: str) -> AIProvider:
    provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()

    if provider_id == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider(api_key)
    if provider_id == "openai":
        from .providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key)
    if provider_id == "deepseek":
        from .providers.deepseek import DeepSeekProvider
        return DeepSeekProvider(api_key)

    raise ProviderError(f"未知 AI 服务商：{provider_id}", provider_id=provider_id)


def list_provider_models(provider_id: str, api_key: str) -> list[str]:
    return create_provider(provider_id, api_key).list_models()


def _resolve_transcriber_id(
    summary_provider_id: str,
    requested: str,
    api_keys: dict[str, str],
) -> str:
    summary_spec = PROVIDERS[summary_provider_id]

    if summary_spec.supports_transcription:
        # OpenAI can transcribe its own audio. Gemini normally bypasses this
        # route because it supports direct audio, but remains valid here.
        return summary_provider_id

    requested = (requested or "auto").strip().lower()
    if requested != "auto":
        spec = PROVIDERS.get(requested)
        if spec is None or not spec.supports_transcription:
            raise ProviderError(
                "所选音频转写服务不可用，请选择 Google Gemini、OpenAI 或自动。",
                provider_id=summary_provider_id,
            )
        if not (api_keys.get(requested) or "").strip():
            raise ProviderError(
                f"{provider_display_name(summary_provider_id)} 不能直接处理音频；"
                f"请先配置 {spec.display_name} API Key 作为音频转写服务。",
                provider_id=summary_provider_id,
            )
        return requested

    # Auto prefers the existing stable Gemini audio path, then OpenAI.
    # Users can still explicitly choose OpenAI in Settings.
    for candidate in ("gemini", "openai"):
        if (api_keys.get(candidate) or "").strip():
            return candidate

    raise ProviderError(
        f"{provider_display_name(summary_provider_id)} 当前不能直接处理音频。"
        "请再配置 OpenAI 或 Google Gemini API Key 用于音频转写，"
        "并在设置中选择对应的转写服务。",
        provider_id=summary_provider_id,
    )


def validate_provider_configuration(
    provider_id: str,
    api_keys: dict[str, str],
    transcription_provider: str = "auto",
) -> None:
    provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()
    if provider_id not in PROVIDERS:
        raise ProviderError(f"未知 AI 服务商：{provider_id}", provider_id=provider_id)

    if not (api_keys.get(provider_id) or "").strip():
        raise ProviderError(
            f"未配置 {provider_display_name(provider_id)} API Key。",
            provider_id=provider_id,
        )

    spec = PROVIDERS[provider_id]
    if not spec.supports_direct_audio and not spec.supports_transcription:
        _resolve_transcriber_id(provider_id, transcription_provider, api_keys)


def summarize_audio_with_provider(
    *,
    audio_path: str | Path,
    provider_id: str,
    api_keys: dict[str, str],
    provider_models: dict[str, str],
    transcription_provider: str,
    transcription_models: dict[str, str],
    progress: ProgressCallback,
) -> str:
    provider_id = (provider_id or DEFAULT_PROVIDER).strip().lower()
    validate_provider_configuration(provider_id, api_keys, transcription_provider)

    summary_key = (api_keys.get(provider_id) or "").strip()
    summary_provider = create_provider(provider_id, summary_key)
    summary_model = (
        (provider_models.get(provider_id) or "").strip()
        or provider_default_model(provider_id)
    )

    if summary_provider.spec.supports_direct_audio:
        return summary_provider.summarize_audio_direct(
            audio_path=audio_path,
            model=summary_model,
            progress=progress,
        )

    transcriber_id = _resolve_transcriber_id(
        provider_id,
        transcription_provider,
        api_keys,
    )
    transcriber = create_provider(
        transcriber_id,
        (api_keys.get(transcriber_id) or "").strip(),
    )
    transcriber_model = (
        (transcription_models.get(transcriber_id) or "").strip()
        or (
            provider_default_model(transcriber_id)
            if transcriber_id != "openai"
            else "gpt-4o-mini-transcribe"
        )
    )

    progress(
        54,
        f"准备使用 {transcriber.spec.display_name} · {transcriber_model} 转写音频…",
    )
    transcript = transcriber.transcribe_audio(
        audio_path=audio_path,
        model=transcriber_model,
        progress=progress,
    )
    if not transcript.strip():
        raise ProviderError(
            "音频转写结果为空，无法继续生成总结。",
            provider_id=provider_id,
        )

    progress(
        70,
        f"音频转写完成，正在提交给 {summary_provider.spec.display_name}…",
    )
    return summary_provider.summarize_text(
        transcript=transcript,
        model=summary_model,
        progress=progress,
    )


__all__ = [
    "ProviderError",
    "create_provider",
    "list_provider_models",
    "summarize_audio_with_provider",
    "validate_provider_configuration",
    "provider_display_name",
    "provider_fallback_models",
]
