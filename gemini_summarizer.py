"""Backward-compatible Gemini facade.

The real provider implementation now lives in ``ai.providers.gemini``.
Keep this module so older imports or external scripts do not break after the
multi-provider refactor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ai.base import ProviderError
from ai.providers.gemini import GeminiProvider

ProgressCallback = Callable[[int, str], None]


class GeminiError(RuntimeError):
    pass


def list_available_models(api_key: str) -> list[str]:
    try:
        return GeminiProvider(api_key).list_models()
    except ProviderError as exc:
        raise GeminiError(str(exc)) from exc


def summarize_audio(
    audio_path: str | Path,
    api_key: str,
    model: str,
    progress: ProgressCallback,
) -> str:
    try:
        return GeminiProvider(api_key).summarize_audio_direct(
            audio_path=audio_path,
            model=model,
            progress=progress,
        )
    except ProviderError as exc:
        raise GeminiError(str(exc)) from exc
