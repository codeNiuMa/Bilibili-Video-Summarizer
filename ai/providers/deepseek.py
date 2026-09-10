from __future__ import annotations

from typing import Any

from ai.base import AIProvider, ProgressCallback, ProviderError
from ai.catalog import PROVIDERS
from ai.prompts import transcript_summary_input


class DeepSeekProvider(AIProvider):
    """DeepSeek adapter using DeepSeek's own HTTP API directly.

    DeepSeek is OpenAI-format compatible, but using the REST API directly
    avoids making the DeepSeek provider depend on the OpenAI Python SDK.
    """

    spec = PROVIDERS["deepseek"]
    BASE_URL = "https://api.deepseek.com"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _error_message(response) -> str:
        try:
            payload: Any = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or "").strip()
                    if message:
                        return message
                message = str(payload.get("message") or "").strip()
                if message:
                    return message
        except Exception:
            pass

        text = str(getattr(response, "text", "") or "").strip()
        return text[:1200] if text else f"HTTP {getattr(response, 'status_code', '?')}"

    def list_models(self) -> list[str]:
        try:
            import httpx
        except ImportError as exc:
            raise ProviderError(
                "缺少 httpx，请重新安装 requirements.txt。",
                provider_id=self.spec.provider_id,
            ) from exc

        try:
            with httpx.Client(
                base_url=self.BASE_URL,
                headers=self._headers(),
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                response = client.get("/models")

            if response.status_code >= 400:
                raise ProviderError(
                    f"DeepSeek 获取模型列表失败："
                    f"HTTP {response.status_code} · {self._error_message(response)}",
                    provider_id=self.spec.provider_id,
                )

            payload = response.json()
            data = payload.get("data", []) if isinstance(payload, dict) else []
            names = sorted({
                str(item.get("id") or "").strip()
                for item in data
                if isinstance(item, dict)
                and str(item.get("id") or "").strip().startswith("deepseek-")
            })

            if not names:
                raise ProviderError(
                    "当前 DeepSeek API 没有返回可用模型。",
                    provider_id=self.spec.provider_id,
                )
            return names

        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"DeepSeek 获取模型列表失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc

    def summarize_text(
        self,
        transcript: str,
        model: str,
        progress: ProgressCallback,
    ) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise ProviderError(
                "缺少 httpx，请重新安装 requirements.txt。",
                provider_id=self.spec.provider_id,
            ) from exc

        try:
            progress(72, f"DeepSeek · {model} 正在总结视频…")

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": transcript_summary_input(transcript),
                    }
                ],
                "stream": False,
            }

            with httpx.Client(
                base_url=self.BASE_URL,
                headers=self._headers(),
                timeout=httpx.Timeout(180.0, connect=30.0),
                follow_redirects=True,
            ) as client:
                response = client.post("/chat/completions", json=payload)

            if response.status_code >= 400:
                raise ProviderError(
                    f"DeepSeek 调用失败："
                    f"HTTP {response.status_code} · {self._error_message(response)}",
                    provider_id=self.spec.provider_id,
                )

            body = response.json()
            choices = body.get("choices", []) if isinstance(body, dict) else []

            text = ""
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message") or {}
                if isinstance(message, dict):
                    text = str(message.get("content") or "").strip()

            if not text:
                raise ProviderError(
                    "DeepSeek 返回了空结果。",
                    provider_id=self.spec.provider_id,
                )

            progress(100, "总结完成")
            return text

        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"DeepSeek 调用失败：{exc}",
                provider_id=self.spec.provider_id,
            ) from exc
