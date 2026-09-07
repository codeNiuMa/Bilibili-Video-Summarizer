from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from .core import (
    MEDIA_EXTENSIONS,
    TEXT_EXTENSIONS,
    MODES,
    STYLES,
    Request,
    Result,
    TaskError,
    normalize_url,
    now,
    parse_subtitle,
    split_text,
    timestamp,
)
from .gemini import Gemini
from .media import Media

STYLE_PROMPTS = {
    "concise": "写一句话结论、3–5 个核心要点和适合谁看，总长约 400 字。",
    "detailed": "写一句话结论、按主题组织的详细笔记、关键论据或例子、结论与局限；保留可追溯时间戳。约 1200–2000 字，素材不足时缩短。",
    "action": "写核心结论、可执行步骤、适用条件与注意事项。资料没有行动建议时明确说明，不擅自编造。",
}


class Pipeline:
    def __init__(
        self, store, settings, token, progress, gemini_factory=Gemini, media_factory=Media
    ):
        self.store, self.settings, self.token, self.progress = store, settings, token, progress
        self.gemini_factory, self.media_factory = gemini_factory, media_factory

    def summarize(self, ai, text, style):
        parts = split_text(text)
        if len(parts) > 1:
            notes = []
            for index, part in enumerate(parts):
                self.token.check()
                self.progress(
                    "整理分段",
                    76 + int(index / len(parts) * 12),
                    f"整理文字片段 {index + 1}/{len(parts)}",
                )
                notes.append(
                    ai.generate(
                        "提取本段的核心事实、观点、数字、例子及原有时间戳，最多 800 字。保留上下文限定条件，不做全篇结论。",
                        text=part,
                    )
                )
            text = "\n\n".join(notes)
        # Hierarchical reduction has an explicit bound and requires shrinking.
        for _ in range(8):
            if len(text) <= 24000:
                break
            previous = len(text)
            reduced = [
                ai.generate(
                    "合并以下局部笔记，去重并保留事实、限定条件和原有时间戳，最多 600 字。", text=p
                )
                for p in split_text(text)
            ]
            text = "\n\n".join(reduced)
            if len(text) >= previous:
                raise TaskError("分段笔记未能收敛，请改用精简模式或处理更短的素材。")
        if len(text) > 24000:
            raise TaskError("素材过长，请拆分为多个任务。")
        self.progress("生成笔记", 92, "正在汇总完整笔记…")
        return ai.generate("根据以下资料整理视频笔记。" + STYLE_PROMPTS[style], text=text)

    def run(self, request: Request, key: str):
        self.token.check()
        if request.mode not in MODES or request.style not in STYLES:
            raise TaskError("未知处理模式或笔记风格。")
        if not key.strip():
            raise TaskError("请先在设置中填写 Gemini API Key。")
        if not 60 <= self.settings.chunk_seconds <= 900:
            raise TaskError("分段时长须为 60–900 秒。")
        source = request.source.strip()
        if not source:
            raise TaskError("请粘贴视频链接或选择本地文件。")
        path = Path(source).expanduser()
        is_local = path.is_file()
        if is_local:
            path = path.resolve()
            source = str(path)
            if path.suffix.lower() not in MEDIA_EXTENSIONS | TEXT_EXTENSIONS:
                raise TaskError("暂不支持此文件类型，请选择常见音视频或字幕文件。")
        else:
            source = normalize_url(source)
        ai = self.gemini_factory(key, self.settings.model, self.store, self.token, self.progress)
        media = self.media_factory(self.settings, self.token, self.progress)
        transcript, input_kind = "", "音频摘要"
        try:
            # All downloads/transcodes are owned by this job. Originals are read-only.
            with tempfile.TemporaryDirectory(prefix="job-", dir=self.store.root / "temp") as temp:
                directory = Path(temp)
                title = path.stem if is_local else "B 站视频"
                if is_local and path.suffix.lower() in TEXT_EXTENSIONS:
                    transcript = parse_subtitle(path.read_text(encoding="utf-8-sig"), path.suffix)
                    if not transcript.strip():
                        raise TaskError("字幕或文字文件为空，无法总结。")
                    input_kind = "本地字幕 / 文字"
                elif not is_local:
                    title, subtitle = media.resolve(
                        source, directory, subtitles=request.mode == "auto"
                    )
                    if subtitle:
                        transcript, input_kind = subtitle, "视频字幕"
                    else:
                        path = media.download(source, directory)
                if transcript:
                    self.progress("读取字幕", 65, "已取得文字，省去音频下载与转写。")
                    summary = self.summarize(ai, transcript, request.style)
                else:
                    chunks = media.split(path, directory)
                    notes = []
                    for index, chunk in enumerate(chunks):
                        self.token.check()
                        offset = timestamp(index * self.settings.chunk_seconds)
                        self.progress(
                            "转写音频" if request.mode == "transcript" else "理解音频",
                            40 + int(index / len(chunks) * 35),
                            f"片段 {index + 1}/{len(chunks)} · 起点 {offset}",
                        )
                        context = f"这是原视频第 {index + 1} 段，起点为 {offset}。所有输出时间戳需加上此起点偏移，使用 HH:MM:SS。"
                        if request.mode == "transcript":
                            prompt = (
                                context
                                + "逐句完整转写，保留原语言，不总结不翻译；适当分段并附时间戳。听不清写[听不清]，没有语音写[无语音]。"
                            )
                        else:
                            prompt = (
                                context
                                + "提取本段核心观点、论据、数字、例子及条件，按主题写中文笔记，最多 800 字。仅为能可靠定位的内容附时间戳。"
                            )
                        notes.append(ai.generate(prompt, audio=chunk))
                    content = "\n\n".join(notes)
                    if request.mode == "transcript":
                        transcript, input_kind = content, "Gemini 音频转写"
                    summary = self.summarize(ai, content, request.style)
                self.token.check()
                result = Result(
                    uuid.uuid4().hex,
                    title,
                    source,
                    self.settings.model,
                    request.mode,
                    now(),
                    summary,
                    transcript,
                    input_kind,
                    ai.cached_calls,
                    ai.api_calls,
                    ai.prompt_tokens,
                    ai.output_tokens,
                )
                self.store.save(result)
                self.progress("已完成", 100, "笔记已保存到本地历史记录。")
                return result
        finally:
            ai.close()
