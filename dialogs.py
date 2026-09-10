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
)

from ui_widgets import APP_FONT_FAMILY


@dataclass(frozen=True)
class FriendlyError:
    title: str
    summary: str
    suggestion: str
    raw: str


def classify_error(raw: str) -> FriendlyError:
    """Convert technical backend exceptions into concise user-facing guidance."""
    raw = (raw or "未知错误").strip()
    low = raw.lower()

    if "503" in low or "high demand" in low or "unavailable" in low:
        return FriendlyError(
            "Gemini 服务暂时繁忙",
            "当前模型暂时无法处理这次请求，通常是服务端短时负载较高。",
            "稍后重新尝试，或在设置中切换其他可用模型。",
            raw,
        )
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return FriendlyError(
            "Gemini 配额暂时不可用",
            "当前 API Key 可能达到请求频率或配额限制。",
            "稍后再试，并检查对应 Gemini API 项目的配额状态。",
            raw,
        )
    if "401" in low or "403" in low or "api key" in low or "permission" in low:
        return FriendlyError(
            "Gemini API Key 无法使用",
            "API Key 可能无效、过期，或当前项目没有相应模型权限。",
            "打开设置重新检查 API Key，然后刷新可用模型。",
            raw,
        )
    if "412" in low or "request was banned" in low:
        return FriendlyError(
            "B 站暂时拒绝了访问",
            "B 站访问策略阻止了本次音频获取，这不是 Gemini 错误。",
            "更新 yt-dlp；若视频需要登录，请在设置中选择自己的 Cookie 文件，或稍后再试。",
            raw,
        )
    if "ffmpeg" in low or "音轨" in raw or "转换失败" in raw:
        return FriendlyError(
            "音频预处理失败",
            "FFmpeg 没能从当前媒体中生成可供 Gemini 使用的音频。",
            "确认文件包含可读取的音轨；必要时查看下载日志中的技术信息。",
            raw,
        )
    if "no such file or directory" in low or "filenotfound" in low:
        return FriendlyError(
            "运行环境缺少所需文件",
            "程序访问某个本地文件或环境资源时发现它不存在。",
            "检查当前 Python/Conda 环境、Cookie 路径和相关依赖配置，再重新尝试。",
            raw,
        )
    if "gemini" in low:
        return FriendlyError(
            "Gemini 处理失败",
            "请求已经进入 Gemini 阶段，但服务没有正常返回总结结果。",
            "可以稍后重试或切换模型；技术详情已保留供排查。",
            raw,
        )
    if "下载" in raw or "yt-dlp" in low or "b站" in low:
        return FriendlyError(
            "视频音频获取失败",
            "程序没有成功获取这条视频的音频。",
            "检查链接、网络和 Cookie 设置，并可打开下载日志查看详细原因。",
            raw,
        )
    return FriendlyError(
        "任务未能完成",
        "处理过程中遇到了一个未预期的问题。",
        "可以重新尝试；如果持续出现，请展开技术详情并查看下载日志。",
        raw,
    )


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
    """Centralized settings for credentials and persistent application options."""

    def __init__(
        self,
        *,
        api_key: str,
        cookie_file: str,
        model: str,
        models: list[str],
        keep_download: bool,
        theme: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(650, 560)
        self.setMinimumSize(590, 520)
        self._api_from_env = bool(os.environ.get("GEMINI_API_KEY", "").strip())

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(16)

        title = QLabel("设置", self)
        title.setObjectName("settingsTitle")
        subtitle = QLabel("统一管理 Gemini、Bilibili 和应用偏好。", self)
        subtitle.setObjectName("settingsMuted")
        root.addWidget(title)
        root.addWidget(subtitle)

        gemini = self._section("Gemini")
        gl = gemini.layout()
        gl.addWidget(self._field_label("API Key"))
        key_row = QHBoxLayout()
        self.api_edit = QLineEdit(gemini)
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_edit.setText(api_key)
        self.api_edit.setPlaceholderText("输入 Gemini API Key")
        self.api_edit.setReadOnly(self._api_from_env)
        key_row.addWidget(self.api_edit, 1)
        self.show_key_button = QPushButton("显示", gemini)
        self.show_key_button.setFixedWidth(72)
        self.show_key_button.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.show_key_button)
        gl.addLayout(key_row)

        if self._api_from_env:
            env_note = QLabel("当前由环境变量 GEMINI_API_KEY 提供，界面中不会覆盖它。", gemini)
            env_note.setObjectName("settingsHint")
            env_note.setWordWrap(True)
            gl.addWidget(env_note)

        gl.addWidget(self._field_label("默认模型"))
        self.model_combo = QComboBox(gemini)
        values = list(dict.fromkeys([m for m in models if m] + ([model] if model else [])))
        self.model_combo.addItems(values)
        if model:
            self.model_combo.setCurrentText(model)
        gl.addWidget(self.model_combo)
        root.addWidget(gemini)

        bili = self._section("Bilibili")
        bl = bili.layout()
        bl.addWidget(self._field_label("Cookie 文件（可选）"))
        cookie_row = QHBoxLayout()
        self.cookie_edit = QLineEdit(bili)
        self.cookie_edit.setReadOnly(True)
        self.cookie_edit.setText(cookie_file)
        self.cookie_edit.setPlaceholderText("未使用 Cookie")
        cookie_row.addWidget(self.cookie_edit, 1)
        choose = QPushButton("选择", bili)
        choose.clicked.connect(self._choose_cookie)
        cookie_row.addWidget(choose)
        clear = QPushButton("清除", bili)
        clear.clicked.connect(self.cookie_edit.clear)
        cookie_row.addWidget(clear)
        bl.addLayout(cookie_row)
        root.addWidget(bili)

        app_section = self._section("应用")
        al = app_section.layout()
        self.keep_check = QCheckBox("保留从 B 站下载的原始音频", app_section)
        self.keep_check.setChecked(bool(keep_download))
        al.addWidget(self.keep_check)

        theme_row = QHBoxLayout()
        theme_label = QLabel("外观主题", app_section)
        theme_label.setObjectName("settingsFieldLabel")
        theme_row.addWidget(theme_label)
        theme_row.addStretch(1)
        self.theme_combo = QComboBox(app_section)
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        index = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        self.theme_combo.setFixedWidth(150)
        theme_row.addWidget(self.theme_combo)
        al.addLayout(theme_row)
        root.addWidget(app_section)

        root.addStretch(1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消", self)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        save = QPushButton("保存设置", self)
        save.setObjectName("settingsPrimaryButton")
        save.clicked.connect(self.accept)
        footer.addWidget(save)
        root.addLayout(footer)
        self._apply_style(theme)

    def _section(self, title: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("settingsSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(9)
        label = QLabel(title, frame)
        label.setObjectName("settingsSectionTitle")
        layout.addWidget(label)
        return frame

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("settingsFieldLabel")
        return label

    def _toggle_key_visibility(self) -> None:
        if self.api_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_button.setText("隐藏")
        else:
            self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_button.setText("显示")

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
        return {
            "api_key": self.api_edit.text().strip(),
            "api_from_env": self._api_from_env,
            "cookie_file": self.cookie_edit.text().strip(),
            "model": self.model_combo.currentText().strip(),
            "keep_download": self.keep_check.isChecked(),
            "theme": str(self.theme_combo.currentData() or "light"),
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
            QLabel#settingsMuted, QLabel#settingsHint {{ color: {muted}; font-size: 10px; }}
            QFrame#settingsSection {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
            QLabel#settingsSectionTitle {{ color: {text}; font-size: 13px; font-weight: 700; }}
            QLabel#settingsFieldLabel {{ color: {muted}; font-size: 10px; font-weight: 600; }}
            QLineEdit, QComboBox {{ min-height: 38px; background: {input_bg}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 0 10px; }}
            QComboBox::drop-down {{ border: none; width: 26px; }}
            QComboBox QAbstractItemView {{ background: {card}; color: {text}; border: 1px solid {border}; }}
            QCheckBox {{ color: {text}; spacing: 8px; font-size: 11px; }}
            QPushButton {{ background: transparent; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px 13px; font-size: 11px; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton#settingsPrimaryButton {{ background: #4F7DF3; color: white; border: none; }}
            QPushButton#settingsPrimaryButton:hover {{ background: #416FE4; }}
            '''
        )
