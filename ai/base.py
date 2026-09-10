from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Callable

from .catalog import ProviderSpec

ProgressCallback = Callable[[int, str], None]


class ProviderError(RuntimeError):
    """Normalized error raised by any AI provider adapter."""

    def __init__(self, message: str, *, provider_id: str = ""):
        super().__init__(message)
        self.provider_id = provider_id


class AIProvider(ABC):
    spec: ProviderSpec

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ProviderError(
                f"未配置 {self.spec.display_name} API Key。",
                provider_id=self.spec.provider_id,
            )

    def list_models(self) -> list[str]:
        raise ProviderError(
            f"{self.spec.display_name} 暂不支持自动获取模型列表。",
            provider_id=self.spec.provider_id,
        )

    def summarize_audio_direct(
        self,
        audio_path: str | Path,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        raise ProviderError(
            f"{self.spec.display_name} 当前适配器不支持直接音频总结。",
            provider_id=self.spec.provider_id,
        )

    def transcribe_audio(
        self,
        audio_path: str | Path,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        raise ProviderError(
            f"{self.spec.display_name} 当前适配器不支持音频转写。",
            provider_id=self.spec.provider_id,
        )

    def summarize_text(
        self,
        transcript: str,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        raise ProviderError(
            f"{self.spec.display_name} 当前适配器不支持文本总结。",
            provider_id=self.spec.provider_id,
        )
