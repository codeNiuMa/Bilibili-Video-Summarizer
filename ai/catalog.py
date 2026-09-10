from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    display_name: str
    env_var: str
    default_model: str
    fallback_models: tuple[str, ...]
    supports_direct_audio: bool
    supports_transcription: bool
    notes: str


PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        provider_id="gemini",
        display_name="Google Gemini",
        env_var="GEMINI_API_KEY",
        default_model="gemini-3.5-flash-lite",
        fallback_models=(
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ),
        supports_direct_audio=True,
        supports_transcription=True,
        notes="Gemini 可直接理解上传的音频，默认沿用当前稳定流程。",
    ),
    "openai": ProviderSpec(
        provider_id="openai",
        display_name="OpenAI",
        env_var="OPENAI_API_KEY",
        default_model="gpt-5-mini",
        fallback_models=(
            "gpt-5-mini",
            "gpt-4.1-mini",
            "gpt-4o",
        ),
        supports_direct_audio=False,
        supports_transcription=True,
        notes="OpenAI 路线先调用语音转写，再由所选文本模型生成视频笔记。",
    ),
    "deepseek": ProviderSpec(
        provider_id="deepseek",
        display_name="DeepSeek",
        env_var="DEEPSEEK_API_KEY",
        default_model="deepseek-v4-flash",
        fallback_models=(
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ),
        supports_direct_audio=False,
        supports_transcription=False,
        notes="DeepSeek 用于文本总结，本身不提供音频转写；音频需先由 Gemini 或 OpenAI 转写。",
    ),
}

DEFAULT_PROVIDER = "gemini"
TRANSCRIPTION_PROVIDER_IDS = ("auto", "gemini", "openai")
OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
OPENAI_TRANSCRIPTION_MODELS = (
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
)


def transcription_model_candidates(
    provider_id: str,
    available_models: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Return sensible selectable models for the transcription role.

    Gemini's general multimodal generation models can accept audio in the
    existing stable path. Obvious image/TTS/live/specialized models are hidden
    from the transcription selector so users are less likely to choose an
    incompatible model.
    """
    provider_id = (provider_id or "").strip().lower()

    if provider_id == "openai":
        return list(OPENAI_TRANSCRIPTION_MODELS)

    if provider_id == "gemini":
        source = list(available_models or []) + provider_fallback_models("gemini")
        excluded = (
            "image",
            "tts",
            "computer-use",
            "computer_use",
            "live",
            "embedding",
            "robotics",
        )
        values: list[str] = []
        for model in source:
            model = str(model or "").strip()
            low = model.lower()
            if not model.startswith("gemini-"):
                continue
            if any(token in low for token in excluded):
                continue
            if model not in values:
                values.append(model)
        return values

    return []


def provider_spec(provider_id: str) -> ProviderSpec:
    return PROVIDERS.get(provider_id, PROVIDERS[DEFAULT_PROVIDER])


def provider_display_name(provider_id: str) -> str:
    return provider_spec(provider_id).display_name


def provider_fallback_models(provider_id: str) -> list[str]:
    return list(provider_spec(provider_id).fallback_models)


def provider_default_model(provider_id: str) -> str:
    return provider_spec(provider_id).default_model
