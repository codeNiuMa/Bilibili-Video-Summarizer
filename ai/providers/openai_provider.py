from __future__ import annotations

from pathlib import Path

from ai.base import AIProvider, ProgressCallback, ProviderError
from ai.catalog import OPENAI_TRANSCRIPTION_MODEL, PROVIDERS
from ai.prompts import transcript_summary_input


class OpenAIProvider(AIProvider):
    spec = PROVIDERS["openai"]

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                "缺少 openai Python SDK，请先重新安装 requirements.txt。",
                provider_id=self.spec.provider_id,
            ) from exc
        return OpenAI(api_key=self.api_key)

    @staticmethod
    def _looks_like_text_model(model_id: str) -> bool:
        model_id = model_id.lower()
        if not (model_id.startswith("gpt-") or model_id.startswith("o")):
            return False
        excluded = (
            "transcribe", "tts", "realtime", "audio", "image", "embedding",
            "moderation", "search", "sora",
        )
        return not any(token in model_id for token in excluded)

    def list_models(self) -> list[str]:
        try:
            client = self._client()
            names = [
                str(getattr(item, "id", "") or "").strip()
                for item in client.models.list().data
            ]
            names = sorted({name for name in names if self._looks_like_text_model(name)})
            if not names:
                raise ProviderError(
                    "当前 OpenAI API Key 没有查询到适合文本总结的模型。",
                    provider_id=self.spec.provider_id,
                )
            return names
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI 获取模型列表失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc

    def transcribe_audio(
        self,
        audio_path: str | Path,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ProviderError("待转写的音频文件不存在。", provider_id=self.spec.provider_id)

        try:
            client = self._client()
            transcription_model = (model or "").strip() or OPENAI_TRANSCRIPTION_MODEL
            progress(55, f"OpenAI · {transcription_model} 正在转写音频…")
            with path.open("rb") as audio_file:
                result = client.audio.transcriptions.create(
                    model=transcription_model,
                    file=audio_file,
                )
            text = str(getattr(result, "text", None) or "").strip()
            if not text:
                raise ProviderError("OpenAI 返回了空转写结果。", provider_id=self.spec.provider_id)
            progress(68, "OpenAI 音频转写完成，正在准备总结…")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI 音频转写失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc

    def summarize_text(
        self,
        transcript: str,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        try:
            client = self._client()
            progress(72, f"OpenAI · {model} 正在总结视频…")
            response = client.responses.create(
                model=model,
                input=transcript_summary_input(transcript),
            )
            text = str(getattr(response, "output_text", None) or "").strip()
            if not text:
                raise ProviderError("OpenAI 返回了空结果。", provider_id=self.spec.provider_id)
            progress(100, "总结完成")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"OpenAI 调用失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc
