from __future__ import annotations

import time
from pathlib import Path

from ai.base import AIProvider, ProgressCallback, ProviderError
from ai.catalog import PROVIDERS
from ai.prompts import SUMMARY_PROMPT, TRANSCRIPTION_PROMPT, transcript_summary_input


class GeminiProvider(AIProvider):
    spec = PROVIDERS["gemini"]

    @staticmethod
    def _state_name(file_obj) -> str:
        state = getattr(file_obj, "state", None)
        if state is None:
            return ""
        return str(getattr(state, "name", state)).upper()

    def _client(self):
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "缺少 google-genai，请先安装项目 requirements.txt 中的依赖。",
                provider_id=self.spec.provider_id,
            ) from exc
        return genai.Client(api_key=self.api_key)

    def list_models(self) -> list[str]:
        try:
            client = self._client()
            names: list[str] = []
            for model in client.models.list():
                name = str(getattr(model, "name", "") or "").strip()
                actions = getattr(model, "supported_actions", None) or []
                normalized = {str(x).replace("_", "").lower() for x in actions}
                if normalized and "generatecontent" not in normalized:
                    continue
                if name.startswith("models/"):
                    name = name[7:]
                if name.startswith("gemini-"):
                    names.append(name)
            names = sorted(set(names))
            if not names:
                raise ProviderError(
                    "当前 API Key 没有查询到可用于内容生成的 Gemini 模型。",
                    provider_id=self.spec.provider_id,
                )
            return names
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Google Gemini 获取模型列表失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc

    def _upload_ready(self, client, audio_path: Path, progress: ProgressCallback):
        uploaded = client.files.upload(file=str(audio_path))
        for _ in range(90):
            state = self._state_name(uploaded)
            if not state or "ACTIVE" in state or "READY" in state:
                return uploaded
            if "FAILED" in state:
                raise ProviderError(
                    "Google Gemini 云端文件处理失败。",
                    provider_id=self.spec.provider_id,
                )
            if "PROCESSING" not in state:
                return uploaded
            progress(62, "Google Gemini 正在处理上传的音频…")
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        raise ProviderError(
            "Google Gemini 处理音频超时。",
            provider_id=self.spec.provider_id,
        )

    def summarize_audio_direct(
        self,
        audio_path: str | Path,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ProviderError("待上传的音频文件不存在。", provider_id=self.spec.provider_id)

        client = None
        uploaded = None
        try:
            client = self._client()
            progress(55, "正在上传音频到 Google Gemini…")
            uploaded = self._upload_ready(client, path, progress)
            progress(72, f"Google Gemini · {model} 正在总结视频…")
            response = client.models.generate_content(
                model=model,
                contents=[SUMMARY_PROMPT, uploaded],
            )
            text = str(getattr(response, "text", None) or "").strip()
            if not text:
                raise ProviderError("Google Gemini 返回了空结果。", provider_id=self.spec.provider_id)
            progress(100, "总结完成")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Google Gemini 调用失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc
        finally:
            if client is not None and uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass

    def transcribe_audio(
        self,
        audio_path: str | Path,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ProviderError("待转写的音频文件不存在。", provider_id=self.spec.provider_id)

        client = None
        uploaded = None
        try:
            client = self._client()
            progress(55, "正在上传音频供 Google Gemini 转写…")
            uploaded = self._upload_ready(client, path, progress)
            progress(64, f"Google Gemini · {model} 正在转写音频…")
            response = client.models.generate_content(
                model=model,
                contents=[TRANSCRIPTION_PROMPT, uploaded],
            )
            text = str(getattr(response, "text", None) or "").strip()
            if not text:
                raise ProviderError("Google Gemini 返回了空转写结果。", provider_id=self.spec.provider_id)
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Google Gemini 音频转写失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc
        finally:
            if client is not None and uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass

    def summarize_text(
        self,
        transcript: str,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        try:
            client = self._client()
            progress(72, f"Google Gemini · {model} 正在总结转写文本…")
            response = client.models.generate_content(
                model=model,
                contents=transcript_summary_input(transcript),
            )
            text = str(getattr(response, "text", None) or "").strip()
            if not text:
                raise ProviderError("Google Gemini 返回了空结果。", provider_id=self.spec.provider_id)
            progress(100, "总结完成")
            return text
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Google Gemini 文本总结失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc
