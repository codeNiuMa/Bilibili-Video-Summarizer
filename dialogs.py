from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QStackedWidget,
    QScrollArea,
)

from ui_widgets import APP_FONT_FAMILY, SmartComboBox
from ai.catalog import PROVIDERS, provider_fallback_models, transcription_model_candidates
from settings import api_key_from_env, model_cache_updated_at, save_model_cache
from workers import ModelRefreshThread


@dataclass(frozen=True)
class FriendlyError:
    title: str
    summary: str
    suggestion: str
    raw: str


def classify_error(raw: str) -> FriendlyError:
    """Convert provider/backend exceptions into concise user-facing guidance."""
    raw = (raw or "未知错误").strip()
    low = raw.lower()

    provider = "AI 服务"
    # Prefer the actual provider name when compatibility-layer wording contains
    # multiple vendor names (for example "DeepSeek ... OpenAI compatible").
    if "deepseek" in low:
        provider = "DeepSeek"
    elif "openai" in low:
        provider = "OpenAI"
    elif "gemini" in low or "google" in low:
        provider = "Google Gemini"

    if "503" in low or "high demand" in low or "unavailable" in low:
        return FriendlyError(f"{provider} 暂时繁忙", "当前模型暂时无法处理这次请求，通常是服务端短时负载较高。", "稍后重新尝试，或切换同一服务商下的其他可用模型。", raw)
    if "429" in low or "resource_exhausted" in low or "quota" in low or "rate limit" in low:
        return FriendlyError(f"{provider} 配额暂时不可用", "当前 API Key 可能达到请求频率、余额或配额限制。", "稍后再试，并检查该服务商控制台中的额度和计费状态。", raw)
    if "401" in low or "403" in low or "api key" in low or "permission" in low or "authentication" in low:
        return FriendlyError(f"{provider} API Key 无法使用", "API Key 可能无效、过期，或当前账号没有所选模型的访问权限。", "打开设置检查当前服务商的 API Key，并刷新可用模型。", raw)
    if "不能直接处理音频" in raw or "音频转写服务" in raw:
        return FriendlyError("需要配置音频转写服务", "当前选择的总结模型不能直接接收音频，因此必须先把音频转成文字。", "在设置中配置 Google Gemini 或 OpenAI API Key，并选择其作为音频转写服务。", raw)
    if "412" in low or "request was banned" in low:
        return FriendlyError("B 站暂时拒绝了访问", "B 站访问策略阻止了本次音频获取，这不是 AI 模型错误。", "更新 yt-dlp；若视频需要登录，请在设置中选择自己的 Cookie 文件，或稍后再试。", raw)
    if "ffmpeg" in low or "音轨" in raw or "转换失败" in raw:
        return FriendlyError("音频预处理失败", "FFmpeg 没能从当前媒体中生成可供 AI 使用的音频。", "确认文件包含可读取的音轨；必要时查看下载日志中的技术信息。", raw)
    if "no such file or directory" in low or "filenotfound" in low:
        return FriendlyError("运行环境缺少所需文件", "程序访问某个本地文件或环境资源时发现它不存在。", "检查当前 Python/Conda 环境、Cookie 路径和相关依赖配置，再重新尝试。", raw)
    if "openai" in low or "deepseek" in low or "gemini" in low or "provider" in low:
        return FriendlyError(f"{provider} 处理失败", "请求已经进入 AI 服务阶段，但没有正常返回总结结果。", "可以稍后重试或切换模型；技术详情已保留供排查。", raw)
    if "下载" in raw or "yt-dlp" in low or "b站" in low:
        return FriendlyError("视频音频获取失败", "程序没有成功获取这条视频的音频。", "检查链接、网络和 Cookie 设置，并可打开下载日志查看详细原因。", raw)
    return FriendlyError("任务未能完成", "处理过程中遇到了一个未预期的问题。", "可以重新尝试；如果持续出现，请展开技术详情并查看下载日志。", raw)


class ToastWidget(QFrame):
    def __init__(self, text: str, kind: str, theme: str, parent=None):
        super().__init__(parent)
        self.setObjectName("toastWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        symbol = {"success": "✓", "warning": "!", "error": "×", "info": "i"}.get(kind, "i")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 16, 11)
        layout.setSpacing(10)

        icon = QLabel(symbol, self)
        icon.setObjectName("toastIcon")
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        label = QLabel(text, self)
        label.setObjectName("toastText")
        label.setWordWrap(True)
        label.setMaximumWidth(320)
        layout.addWidget(label, 1)

        dark = theme == "dark"
        bg = "#232831" if dark else "#FFFFFF"
        border = "#353C49" if dark else "#DCE2EC"
        text_color = "#F2F4F8" if dark else "#18202A"
        icon_bg = {
            "success": "#2FA572",
            "warning": "#D7952D",
            "error": "#D84A4A",
            "info": "#4F7DF3",
        }.get(kind, "#4F7DF3")

        self.setStyleSheet(
            f'''
            QFrame#toastWidget {{ background: {bg}; border: 1px solid {border}; border-radius: 12px; }}
            QLabel#toastText {{ color: {text_color}; font-family: "{APP_FONT_FAMILY}"; font-size: 11px; border: none; }}
            QLabel#toastIcon {{
                color: white; background: {icon_bg}; border: none; border-radius: 12px;
                font-family: "{APP_FONT_FAMILY}"; font-size: 12px; font-weight: 700;
            }}
            '''
        )
        self.setFixedWidth(390)
        self.adjustSize()
        self.setMinimumHeight(48)


class ToastManager:
    """Non-blocking feedback for lightweight success/warning/info messages."""

    def __init__(self, host: QWidget):
        self.host = host
        self.toast: ToastWidget | None = None
        self.effect: QGraphicsOpacityEffect | None = None
        self.animation: QPropertyAnimation | None = None
        self.timer = QTimer(host)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)

    def show(self, text: str, kind: str = "info", duration: int = 2600) -> None:
        self.clear()
        theme = getattr(self.host.window(), "theme", "light")
        toast = ToastWidget(text, kind, theme, self.host)
        effect = QGraphicsOpacityEffect(toast)
        effect.setOpacity(0.0)
        toast.setGraphicsEffect(effect)

        self.toast = toast
        self.effect = effect
        self.reposition()
        toast.show()
        toast.raise_()

        animation = QPropertyAnimation(effect, b"opacity", toast)
        animation.setDuration(150)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation = animation
        animation.start()
        self.timer.start(max(800, int(duration)))

    def reposition(self) -> None:
        if self.toast is None:
            return
        margin = 24
        x = max(margin, self.host.width() - self.toast.width() - margin)
        y = max(margin, self.host.height() - self.toast.height() - margin)
        self.toast.move(x, y)
        self.toast.raise_()

    def _fade_out(self) -> None:
        if self.toast is None or self.effect is None:
            return
        toast = self.toast
        effect = self.effect
        animation = QPropertyAnimation(effect, b"opacity", toast)
        animation.setDuration(180)
        animation.setStartValue(effect.opacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InCubic)
        animation.finished.connect(self.clear)
        self.animation = animation
        animation.start()

    def clear(self) -> None:
        self.timer.stop()
        if self.animation is not None:
            self.animation.stop()
            self.animation = None
        if self.toast is not None:
            self.toast.hide()
            self.toast.deleteLater()
            self.toast = None
        self.effect = None


class FriendlyErrorDialog(QDialog):
    def __init__(
        self,
        error: FriendlyError,
        *,
        theme: str = "light",
        log_path: Path | None = None,
        on_open_log: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.error = error
        self.log_path = Path(log_path) if log_path else None
        self.on_open_log = on_open_log
        self.setWindowTitle(error.title)
        self.setModal(True)
        self.resize(620, 330)
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        icon = QLabel("×", self)
        icon.setObjectName("errorHeroIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)
        title = QLabel(error.title, self)
        title.setObjectName("errorTitle")
        summary = QLabel(error.summary, self)
        summary.setObjectName("errorSummary")
        summary.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(summary)
        title_row.addLayout(title_box, 1)
        root.addLayout(title_row)

        suggestion_card = QFrame(self)
        suggestion_card.setObjectName("suggestionCard")
        suggestion_layout = QVBoxLayout(suggestion_card)
        suggestion_layout.setContentsMargins(14, 12, 14, 12)
        suggestion_layout.setSpacing(4)
        suggestion_title = QLabel("建议", suggestion_card)
        suggestion_title.setObjectName("errorSectionTitle")
        suggestion = QLabel(error.suggestion, suggestion_card)
        suggestion.setObjectName("errorSuggestion")
        suggestion.setWordWrap(True)
        suggestion_layout.addWidget(suggestion_title)
        suggestion_layout.addWidget(suggestion)
        root.addWidget(suggestion_card)

        self.details = QTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setPlainText(error.raw)
        self.details.setMinimumHeight(150)
        self.details.hide()
        root.addWidget(self.details)

        footer = QHBoxLayout()
        self.details_button = QPushButton("查看技术详情", self)
        self.details_button.clicked.connect(self._toggle_details)
        footer.addWidget(self.details_button)

        copy_button = QPushButton("复制详情", self)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(error.raw))
        footer.addWidget(copy_button)

        if self.log_path is not None and self.on_open_log is not None:
            log_button = QPushButton("打开日志", self)
            log_button.clicked.connect(self._open_log)
            footer.addWidget(log_button)

        footer.addStretch(1)
        close_button = QPushButton("知道了", self)
        close_button.setObjectName("errorPrimaryButton")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)
        self._apply_style(theme)

    def _toggle_details(self) -> None:
        visible = not self.details.isVisible()
        self.details.setVisible(visible)
        self.details_button.setText("收起技术详情" if visible else "查看技术详情")
        self.resize(self.width(), 520 if visible else 330)

    def _open_log(self) -> None:
        if self.on_open_log is not None:
            self.on_open_log()

    def _apply_style(self, theme: str) -> None:
        dark = theme == "dark"
        bg = "#181C23" if dark else "#FFFFFF"
        soft = "#202631" if dark else "#F5F7FB"
        border = "#2A303A" if dark else "#DFE4EC"
        text = "#F2F4F8" if dark else "#161B22"
        muted = "#929CAA" if dark else "#687384"
        hover = "#252B35" if dark else "#EEF1F6"
        self.setStyleSheet(
            f'''
            QDialog {{ background: {bg}; }}
            QLabel, QPushButton, QTextEdit {{ font-family: "{APP_FONT_FAMILY}"; }}
            QLabel#errorHeroIcon {{ background: #D84A4A; color: white; border-radius: 21px; font-size: 24px; font-weight: 500; }}
            QLabel#errorTitle {{ color: {text}; font-size: 18px; font-weight: 700; }}
            QLabel#errorSummary, QLabel#errorSuggestion {{ color: {muted}; font-size: 11px; }}
            QLabel#errorSectionTitle {{ color: {text}; font-size: 11px; font-weight: 700; }}
            QFrame#suggestionCard {{ background: {soft}; border: 1px solid {border}; border-radius: 10px; }}
            QTextEdit {{ background: {soft}; color: {text}; border: 1px solid {border}; border-radius: 9px; padding: 10px; font-size: 10px; }}
            QPushButton {{ background: transparent; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px 12px; font-size: 11px; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton#errorPrimaryButton {{ background: #4F7DF3; color: white; border: none; }}
            QPushButton#errorPrimaryButton:hover {{ background: #416FE4; }}
            '''
        )


class SettingsDialog(QDialog):
    """Multi-provider settings for credentials, models and audio transcription."""

    def __init__(
        self,
        *,
        provider_id: str,
        api_keys: dict[str, str],
        provider_models: dict[str, str],
        models_by_provider: dict[str, list[str]],
        transcription_provider: str,
        transcription_models: dict[str, str],
        cookie_file: str,
        keep_download: bool,
        theme: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(740, 700)
        self.setMinimumSize(660, 600)

        self._api_edits: dict[str, QLineEdit] = {}
        self._show_key_buttons: dict[str, QPushButton] = {}
        self._model_combos: dict[str, SmartComboBox] = {}
        self._model_refresh_buttons: dict[str, QPushButton] = {}
        self._model_status_labels: dict[str, QLabel] = {}
        self._api_from_env: dict[str, bool] = {}
        self._model_refresh_thread: ModelRefreshThread | None = None
        self._refreshing_provider_id = ""
        self._models_by_provider = {
            pid: list(values)
            for pid, values in models_by_provider.items()
        }
        self._transcription_models = dict(transcription_models)
        self._active_transcription_model_provider = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(18)

        title = QLabel("设置", self)
        title.setObjectName("settingsTitle")
        subtitle = QLabel("统一管理 AI 服务商、API Key、模型和 Bilibili 偏好。", self)
        subtitle.setObjectName("settingsMuted")
        root.addWidget(title)
        root.addWidget(subtitle)

        # Scrollable body prevents DPI/small-screen layout compression.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(16)
        scroll.setWidget(body)

        ai_section = self._section("AI 服务")
        ai_section.setMinimumHeight(455)
        al = ai_section.layout()

        al.addWidget(self._field_label("当前服务商"))
        self.provider_combo = SmartComboBox(ai_section, max_visible_items=8, max_popup_width=520)
        self.provider_combo.setMinimumHeight(42)
        for pid, spec in PROVIDERS.items():
            self.provider_combo.addItem(spec.display_name, pid)
        idx = self.provider_combo.findData(provider_id)
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        al.addWidget(self.provider_combo)

        self.provider_stack = QStackedWidget(ai_section)
        self.provider_stack.setMinimumHeight(190)
        for pid, spec in PROVIDERS.items():
            page = QWidget(self.provider_stack)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 8, 0, 4)
            page_layout.setSpacing(10)

            page_layout.addWidget(self._field_label(f"{spec.display_name} API Key"))
            key_row = QHBoxLayout()
            key_row.setSpacing(10)
            edit = QLineEdit(page)
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setText(str(api_keys.get(pid) or ""))
            edit.setPlaceholderText(f"输入 {spec.display_name} API Key")
            edit.setMinimumHeight(42)
            from_env = api_key_from_env(pid)
            edit.setReadOnly(from_env)
            key_row.addWidget(edit, 1)

            show = QPushButton("显示", page)
            show.setFixedSize(76, 42)
            show.clicked.connect(lambda _checked=False, p=pid: self._toggle_key_visibility(p))
            key_row.addWidget(show)
            page_layout.addLayout(key_row)

            self._api_edits[pid] = edit
            self._show_key_buttons[pid] = show
            self._api_from_env[pid] = from_env

            if from_env:
                env_note = QLabel(
                    f"当前由环境变量 {spec.env_var} 提供，界面不会覆盖它。",
                    page,
                )
                env_note.setObjectName("settingsHint")
                env_note.setWordWrap(True)
                page_layout.addWidget(env_note)

            page_layout.addWidget(self._field_label("默认总结模型"))

            model_row = QHBoxLayout()
            model_row.setSpacing(10)

            combo = SmartComboBox(page, max_visible_items=9, max_popup_width=560)
            # 设置页中的模型仅允许从已发现/已缓存列表选择。
            combo.setEditable(False)
            combo.setMinimumHeight(42)
            candidates = list(dict.fromkeys(
                [x for x in models_by_provider.get(pid, []) if x]
                + provider_fallback_models(pid)
                + ([provider_models.get(pid, "")] if provider_models.get(pid) else [])
            ))
            combo.addItems(candidates)
            current_model = str(provider_models.get(pid) or spec.default_model)
            combo.setCurrentText(current_model)
            model_row.addWidget(combo, 1)

            refresh = QPushButton("刷新模型", page)
            refresh.setObjectName("settingsRefreshButton")
            refresh.setFixedSize(92, 42)
            refresh.setToolTip(f"从 {spec.display_name} 获取最新可用模型并缓存到本地")
            refresh.clicked.connect(
                lambda _checked=False, p=pid: self._refresh_provider_models(p)
            )
            model_row.addWidget(refresh)

            page_layout.addLayout(model_row)
            self._model_combos[pid] = combo
            self._model_refresh_buttons[pid] = refresh

            cache_status = QLabel("", page)
            cache_status.setObjectName("settingsCacheHint")
            cache_status.setWordWrap(True)
            updated_at = model_cache_updated_at(pid)
            if updated_at:
                cache_status.setText("已载入本地模型缓存，可按需刷新。")
            else:
                cache_status.setText("当前为内置模型列表；刷新成功后会自动缓存到本地。")
            page_layout.addWidget(cache_status)
            self._model_status_labels[pid] = cache_status

            note = QLabel(spec.notes, page)
            note.setObjectName("settingsHint")
            note.setWordWrap(True)
            page_layout.addWidget(note)
            page_layout.addStretch(1)

            self.provider_stack.addWidget(page)

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self._provider_changed(self.provider_combo.currentIndex())
        al.addWidget(self.provider_stack)

        al.addWidget(self._field_label("音频转写服务"))
        self.transcription_combo = SmartComboBox(ai_section, max_visible_items=6, max_popup_width=420)
        self.transcription_combo.setMinimumHeight(42)
        self.transcription_combo.addItem("自动选择", "auto")
        self.transcription_combo.addItem("Google Gemini", "gemini")
        self.transcription_combo.addItem("OpenAI", "openai")
        trans_idx = self.transcription_combo.findData(transcription_provider)
        self.transcription_combo.setCurrentIndex(trans_idx if trans_idx >= 0 else 0)
        al.addWidget(self.transcription_combo)

        al.addWidget(self._field_label("音频转写模型"))
        self.transcription_model_combo = SmartComboBox(
            ai_section,
            max_visible_items=9,
            max_popup_width=560,
        )
        self.transcription_model_combo.setMinimumHeight(42)
        al.addWidget(self.transcription_model_combo)

        self.transcription_resolution_label = QLabel("", ai_section)
        self.transcription_resolution_label.setObjectName("settingsHint")
        self.transcription_resolution_label.setWordWrap(True)
        al.addWidget(self.transcription_resolution_label)

        trans_note = QLabel(
            "仅当所选总结服务商不能直接处理音频时使用。DeepSeek 需要先通过 Gemini 或 OpenAI 转写；"
            "自动模式优先使用已配置的 Gemini，其次 OpenAI。转写模型与总结模型独立保存。",
            ai_section,
        )
        trans_note.setObjectName("settingsHint")
        trans_note.setWordWrap(True)
        al.addWidget(trans_note)

        self.transcription_combo.currentIndexChanged.connect(
            self._refresh_transcription_controls
        )
        self.transcription_model_combo.currentTextChanged.connect(
            self._transcription_model_changed
        )
        for edit in self._api_edits.values():
            edit.textChanged.connect(self._refresh_transcription_controls)

        self._refresh_transcription_controls()
        body_layout.addWidget(ai_section)

        bili = self._section("Bilibili")
        bili.setMinimumHeight(132)
        bl = bili.layout()
        bl.addWidget(self._field_label("Cookie 文件（可选）"))
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(10)
        self.cookie_edit = QLineEdit(bili)
        self.cookie_edit.setReadOnly(True)
        self.cookie_edit.setText(cookie_file)
        self.cookie_edit.setPlaceholderText("未使用 Cookie")
        self.cookie_edit.setMinimumHeight(42)
        cookie_row.addWidget(self.cookie_edit, 1)
        choose = QPushButton("选择", bili)
        choose.setFixedHeight(42)
        choose.clicked.connect(self._choose_cookie)
        cookie_row.addWidget(choose)
        clear = QPushButton("清除", bili)
        clear.setFixedHeight(42)
        clear.clicked.connect(self.cookie_edit.clear)
        cookie_row.addWidget(clear)
        bl.addLayout(cookie_row)
        body_layout.addWidget(bili)

        app_section = self._section("应用")
        app_section.setMinimumHeight(86)
        app_layout = app_section.layout()
        self.keep_check = QCheckBox("保留从 B 站下载的原始音频", app_section)
        self.keep_check.setChecked(bool(keep_download))
        self.keep_check.setMinimumHeight(32)
        app_layout.addWidget(self.keep_check)
        body_layout.addWidget(app_section)
        body_layout.addStretch(1)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("保存设置", self)
        self.save_button.setObjectName("settingsPrimaryButton")
        self.save_button.clicked.connect(self.accept)
        footer.addWidget(self.save_button)
        root.addLayout(footer)

        self._apply_style(theme)

    def _section(self, title: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("settingsSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(11)
        label = QLabel(title, frame)
        label.setObjectName("settingsSectionTitle")
        layout.addWidget(label)
        return frame

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("settingsFieldLabel")
        label.setMinimumHeight(18)
        return label

    def _provider_changed(self, index: int) -> None:
        if 0 <= index < self.provider_stack.count():
            self.provider_stack.setCurrentIndex(index)

    def _toggle_key_visibility(self, provider_id: str) -> None:
        edit = self._api_edits[provider_id]
        button = self._show_key_buttons[provider_id]
        if edit.echoMode() == QLineEdit.EchoMode.Password:
            edit.setEchoMode(QLineEdit.EchoMode.Normal)
            button.setText("隐藏")
        else:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            button.setText("显示")

    def _refresh_provider_models(self, provider_id: str) -> None:
        provider_id = (provider_id or "").strip().lower()
        if provider_id not in PROVIDERS:
            return

        if self._model_refresh_thread and self._model_refresh_thread.isRunning():
            return

        edit = self._api_edits.get(provider_id)
        api_key = edit.text().strip() if edit is not None else ""
        status = self._model_status_labels.get(provider_id)

        if not api_key:
            if status is not None:
                status.setText("请先填写该服务商的 API Key，再刷新模型列表。")
            return

        self._refreshing_provider_id = provider_id
        button = self._model_refresh_buttons.get(provider_id)
        if button is not None:
            button.setEnabled(False)
            button.setText("刷新中…")

        # Avoid closing/destroying the dialog while its QThread is running.
        if hasattr(self, "save_button"):
            self.save_button.setEnabled(False)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(False)

        if status is not None:
            status.setText(
                f"正在从 {PROVIDERS[provider_id].display_name} 获取最新模型列表…"
            )

        thread = ModelRefreshThread(provider_id, api_key, self)
        self._model_refresh_thread = thread
        thread.models_ready.connect(self._settings_models_ready)
        thread.failed.connect(self._settings_models_failed)
        thread.finished.connect(self._settings_models_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _settings_models_ready(self, provider_id: str, models: list[str]) -> None:
        models = list(dict.fromkeys(
            str(model).strip()
            for model in models
            if str(model).strip()
        ))
        if not models:
            self._settings_models_failed(
                provider_id,
                "服务商没有返回可用模型。",
            )
            return

        self._models_by_provider[provider_id] = list(models)
        save_model_cache(provider_id, models)

        combo = self._model_combos.get(provider_id)
        if combo is not None:
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(models)

            if current and current in models:
                combo.setCurrentText(current)
            elif combo.count():
                combo.setCurrentIndex(0)

            combo.blockSignals(False)

        status = self._model_status_labels.get(provider_id)
        if status is not None:
            status.setText(
                f"已刷新 {len(models)} 个模型，并缓存到本地。下次启动无需再次刷新。"
            )

        # A refreshed Gemini list may also change the selectable transcription
        # models, so update that selector immediately.
        if provider_id in {"gemini", "openai"}:
            self._refresh_transcription_controls()

    def _settings_models_failed(self, provider_id: str, message: str) -> None:
        status = self._model_status_labels.get(provider_id)
        if status is not None:
            status.setText(
                f"刷新失败：{str(message or '未知错误').strip()}。"
                " 已保留原有本地缓存。"
            )

    def _settings_models_finished(self) -> None:
        provider_id = self._refreshing_provider_id
        button = self._model_refresh_buttons.get(provider_id)
        if button is not None:
            button.setEnabled(True)
            button.setText("刷新模型")

        if hasattr(self, "save_button"):
            self.save_button.setEnabled(True)
        if hasattr(self, "cancel_button"):
            self.cancel_button.setEnabled(True)

        self._model_refresh_thread = None
        self._refreshing_provider_id = ""

    def _resolved_transcription_provider(self) -> str:
        requested = str(self.transcription_combo.currentData() or "auto")
        if requested in {"gemini", "openai"}:
            return requested

        # Must mirror ai.manager._resolve_transcriber_id().
        if self._api_edits.get("gemini") and self._api_edits["gemini"].text().strip():
            return "gemini"
        if self._api_edits.get("openai") and self._api_edits["openai"].text().strip():
            return "openai"
        return ""

    def _save_visible_transcription_model(self) -> None:
        provider_id = self._active_transcription_model_provider
        if not provider_id:
            return
        model = self.transcription_model_combo.currentText().strip()
        if model:
            self._transcription_models[provider_id] = model

    def _transcription_model_changed(self, text: str) -> None:
        provider_id = self._active_transcription_model_provider
        text = str(text or "").strip()
        if provider_id and text:
            self._transcription_models[provider_id] = text
            self._update_transcription_resolution_label()

    def _refresh_transcription_controls(self, *_args) -> None:
        # Preserve the model selected for the previously visible transcriber.
        if hasattr(self, "transcription_model_combo"):
            self._save_visible_transcription_model()

        provider_id = self._resolved_transcription_provider()
        self._active_transcription_model_provider = provider_id

        combo = self.transcription_model_combo
        combo.blockSignals(True)
        combo.clear()

        if not provider_id:
            combo.addItem("请先配置 Gemini 或 OpenAI API Key")
            combo.setEnabled(False)
            combo.blockSignals(False)
            self._update_transcription_resolution_label()
            return

        available = self._models_by_provider.get(provider_id, [])
        candidates = transcription_model_candidates(provider_id, available)

        saved = str(self._transcription_models.get(provider_id) or "").strip()
        if saved and saved not in candidates:
            candidates.insert(0, saved)

        if not candidates:
            candidates = [saved] if saved else []

        combo.addItems([x for x in candidates if x])

        if saved:
            combo.setCurrentText(saved)
        elif combo.count():
            self._transcription_models[provider_id] = combo.itemText(0)
            combo.setCurrentIndex(0)

        combo.setEnabled(combo.count() > 0)
        combo.blockSignals(False)
        self._update_transcription_resolution_label()

    def _update_transcription_resolution_label(self) -> None:
        provider_id = self._active_transcription_model_provider
        requested = str(self.transcription_combo.currentData() or "auto")

        if not provider_id:
            self.transcription_resolution_label.setText(
                "当前没有可用的音频转写服务。请先配置 Google Gemini 或 OpenAI API Key。"
            )
            return

        provider_name = PROVIDERS[provider_id].display_name
        model = self.transcription_model_combo.currentText().strip() or "未选择模型"

        if requested == "auto":
            self.transcription_resolution_label.setText(
                f"自动选择当前解析为：{provider_name} · {model}"
            )
        else:
            self.transcription_resolution_label.setText(
                f"实际转写将使用：{provider_name} · {model}"
            )

    def _choose_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Netscape 格式 Cookie 文件",
            "",
            "Cookie text (*.txt);;All files (*.*)",
        )
        if path:
            self.cookie_edit.setText(path)

    def values(self) -> dict[str, object]:
        self._save_visible_transcription_model()
        provider_id = str(self.provider_combo.currentData() or "gemini")
        return {
            "provider": provider_id,
            "api_keys": {pid: edit.text().strip() for pid, edit in self._api_edits.items()},
            "api_from_env": dict(self._api_from_env),
            "provider_models": {pid: combo.currentText().strip() for pid, combo in self._model_combos.items()},
            "transcription_provider": str(self.transcription_combo.currentData() or "auto"),
            "transcription_models": dict(self._transcription_models),
            "cookie_file": self.cookie_edit.text().strip(),
            "keep_download": self.keep_check.isChecked(),
        }

    def _apply_style(self, theme: str) -> None:
        dark = theme == "dark"
        bg = "#14171D" if dark else "#F5F7FB"
        card = "#181C23" if dark else "#FFFFFF"
        input_bg = "#1E232C" if dark else "#F8F9FB"
        border = "#2A303A" if dark else "#DFE4EC"
        text = "#F2F4F8" if dark else "#141820"
        muted = "#929CAA" if dark else "#747E8C"
        hover = "#252B35" if dark else "#EEF1F6"
        self.setStyleSheet(
            f'''
            QDialog {{ background: {bg}; }}
            QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox {{ font-family: "{APP_FONT_FAMILY}"; }}
            QLabel#settingsTitle {{ color: {text}; font-size: 22px; font-weight: 800; }}
            QLabel#settingsMuted, QLabel#settingsHint, QLabel#settingsCacheHint {{
                color: {muted}; font-size: 10px;
            }}
            QFrame#settingsSection {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
            QLabel#settingsSectionTitle {{ color: {text}; font-size: 13px; font-weight: 700; }}
            QLabel#settingsFieldLabel {{ color: {muted}; font-size: 10px; font-weight: 600; }}
            QLineEdit, QComboBox {{
                min-height: 40px; background: {input_bg}; color: {text};
                border: 1px solid {border}; border-radius: 8px;
            }}
            QLineEdit {{ padding: 0 10px; }}
            QComboBox {{ padding: 0 34px 0 10px; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                border: none;
                width: 32px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background: {card}; color: {text};
                selection-background-color: #4F7DF3; selection-color: white;
                border: 1px solid {border}; outline: 0; padding: 3px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 30px;
                padding: 4px 8px;
            }}
            QStackedWidget {{ background: transparent; border: none; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QCheckBox {{ color: {text}; spacing: 8px; font-size: 11px; }}
            QPushButton {{ background: transparent; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px 13px; font-size: 11px; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton#settingsRefreshButton {{
                background: transparent;
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 7px 10px;
            }}
            QPushButton#settingsRefreshButton:hover {{ background: {hover}; }}
            QPushButton#settingsRefreshButton:disabled {{ color: {muted}; }}
            QPushButton#settingsPrimaryButton {{ background: #4F7DF3; color: white; border: none; }}
            QPushButton#settingsPrimaryButton:hover {{ background: #416FE4; }}
            '''
        )
