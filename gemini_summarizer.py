from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[int, str], None]

SUMMARY_PROMPT = """
你是一名中文视频内容整理助手。请仔细听完整段音频，然后输出高质量 Markdown 视频笔记。

要求：
1. 先写「一句话总结」，说明视频最核心的主题和结论。
2. 写「核心内容」，按视频实际逻辑整理 5-10 个要点；不要机械凑数。
3. 对重要概念、论据、步骤、数据、例子进行解释，保留真正有信息量的内容。
4. 写「值得记住的结论」，提炼 3-6 条最有价值的信息。
5. 如果视频包含教程或操作流程，再增加「操作步骤」；如果没有就不要生成这一节。
6. 过滤片头片尾、关注点赞、重复口头禅、无意义寒暄和广告式废话。
7. 不要编造音频中没有的信息。听不清或无法确认的内容应明确说明。
8. 输出中文 Markdown，不要写“作为 AI”等无关说明。
""".strip()


class GeminiError(RuntimeError):
    pass

def list_available_models(api_key: str) -> list[str]:
    """根据当前 API Key 获取可用于 generateContent 的 Gemini 模型。"""
    from google import genai

    if not api_key.strip():
        raise GeminiError("未配置 Gemini API Key。")

    try:
        client = genai.Client(api_key=api_key.strip())

        models = []

        for model in client.models.list():
            name = (getattr(model, "name", "") or "").strip()
            actions = getattr(model, "supported_actions", None) or []

            # 只保留支持文本/多模态生成的 Gemini 模型
            if "generateContent" not in actions:
                continue

            if name.startswith("models/"):
                name = name[7:]

            if not name.startswith("gemini-"):
                continue

            models.append(name)

        # 去重并排序
        models = sorted(set(models))

        if not models:
            raise GeminiError("当前 API Key 没有查询到可用的 Gemini 生成模型。")

        return models

    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"获取 Gemini 模型列表失败：{exc}") from exc

def _state_name(file_obj) -> str:
    state = getattr(file_obj, "state", None)
    if state is None:
        return ""
    return str(getattr(state, "name", state)).upper()


def summarize_audio(
    audio_path: str | Path,
    api_key: str,
    model: str,
    progress: ProgressCallback,
) -> str:
    from google import genai

    audio_path = Path(audio_path).resolve()
    if not api_key.strip():
        raise GeminiError("未配置 Gemini API Key。")
    if not audio_path.is_file():
        raise GeminiError("待上传的音频文件不存在。")

    client = None
    uploaded = None

    try:
        client = genai.Client(api_key=api_key.strip())

        progress(55, "正在上传音频到 Gemini…")
        uploaded = client.files.upload(file=str(audio_path))

        # Most audio files are ready quickly, but Files API may report PROCESSING.
        for _ in range(90):
            state = _state_name(uploaded)
            if not state or "ACTIVE" in state or "READY" in state:
                break
            if "FAILED" in state:
                raise GeminiError("Gemini 云端文件处理失败。")
            if "PROCESSING" not in state:
                break
            progress(62, "Gemini 正在处理上传的音频…")
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        else:
            raise GeminiError("Gemini 处理音频超时。")

        progress(72, f"{model} 正在总结视频…")
        response = client.models.generate_content(
            model=model,
            contents=[SUMMARY_PROMPT, uploaded],
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise GeminiError("Gemini 返回了空结果。")

        progress(100, "总结完成")
        return text
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini 调用失败：{exc}") from exc
    finally:
        if client is not None and uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
