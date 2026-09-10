from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QPointF,
    Property,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSettings,
    QSize,
    QThread,
    QTimer,
    Qt,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from downloader import MediaError, download_bilibili_audio, normalize_audio
from gemini_summarizer import GeminiError, summarize_audio
from settings import (
    DOWNLOAD_DIR,
    LOG_DIR,
    load_api_key,
    load_settings,
    save_api_key,
    save_settings,
)

SUPPORTED_MEDIA = (
    ".m4s",
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".aac",
    ".flac",
    ".ogg",
    ".webm",
    ".mkv",
    ".mov",
)

FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

APP_ORG = "codeNiuMa"
APP_NAME = "Bilibili Video Summarizer"

# Unified application typography.
# Chinese and Latin text both use Microsoft YaHei UI.
# Segoe UI Emoji is kept only as a fallback for emoji glyphs.
APP_FONT_FAMILY = "Microsoft YaHei UI"
APP_EMOJI_FAMILY = "Segoe UI Emoji"
APP_FONT_SIZE = 10


def _paint_icon(kind: str, color: str, size: int = 18) -> QPixmap:
    """Draw small Fluent-like line icons without relying on emoji/icon fonts."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    scale = size / 18.0
    painter.scale(scale, scale)

    if kind == "minimize":
        painter.drawLine(QPointF(4.2, 9.0), QPointF(13.8, 9.0))
    elif kind == "maximize":
        painter.drawRoundedRect(QRectF(4.2, 4.2, 9.6, 9.6), 0.7, 0.7)
    elif kind == "restore":
        painter.drawRoundedRect(QRectF(5.1, 6.0, 8.0, 7.2), 0.6, 0.6)
        painter.drawLine(QPointF(7.0, 4.6), QPointF(13.6, 4.6))
        painter.drawLine(QPointF(13.6, 4.6), QPointF(13.6, 11.0))
        painter.drawLine(QPointF(7.0, 4.6), QPointF(7.0, 5.9))
    elif kind == "close":
        painter.drawLine(QPointF(5.0, 5.0), QPointF(13.0, 13.0))
        painter.drawLine(QPointF(13.0, 5.0), QPointF(5.0, 13.0))
    elif kind == "refresh":
        painter.drawArc(QRectF(3.4, 3.4, 11.2, 11.2), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(12.2, 3.9), QPointF(14.6, 3.7))
        painter.drawLine(QPointF(14.6, 3.7), QPointF(14.0, 6.1))
    elif kind == "sun":
        painter.drawEllipse(QRectF(6.0, 6.0, 6.0, 6.0))
        for a, b in [
            ((9, 2.5), (9, 4.2)), ((9, 13.8), (9, 15.5)),
            ((2.5, 9), (4.2, 9)), ((13.8, 9), (15.5, 9)),
            ((4.3, 4.3), (5.5, 5.5)), ((12.5, 12.5), (13.7, 13.7)),
            ((12.5, 5.5), (13.7, 4.3)), ((4.3, 13.7), (5.5, 12.5)),
        ]:
            painter.drawLine(QPointF(*a), QPointF(*b))
    elif kind == "moon":
        path = QPainterPath()
        path.moveTo(12.8, 3.5)
        path.cubicTo(8.3, 3.8, 6.0, 6.2, 6.0, 9.0)
        path.cubicTo(6.0, 12.1, 8.4, 14.2, 12.4, 14.4)
        path.cubicTo(10.8, 15.1, 9.4, 15.4, 8.0, 15.2)
        path.cubicTo(4.5, 14.8, 2.8, 12.1, 2.8, 9.0)
        path.cubicTo(2.8, 5.3, 5.6, 2.5, 9.4, 2.5)
        path.cubicTo(10.7, 2.5, 11.8, 2.9, 12.8, 3.5)
        painter.drawPath(path)
    elif kind == "key":
        painter.drawEllipse(QRectF(3.0, 4.7, 5.8, 5.8))
        painter.drawLine(QPointF(8.1, 9.3), QPointF(14.8, 14.0))
        painter.drawLine(QPointF(12.2, 12.2), QPointF(13.6, 10.8))
        painter.drawLine(QPointF(13.5, 13.1), QPointF(14.8, 11.8))
    elif kind == "cookie":
        painter.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(6.0, 6.0, 1.6, 1.6))
        painter.drawEllipse(QRectF(10.4, 6.9, 1.5, 1.5))
        painter.drawEllipse(QRectF(8.0, 10.5, 1.5, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "log":
        painter.drawRoundedRect(QRectF(4.0, 2.8, 10.0, 12.4), 1.1, 1.1)
        painter.drawLine(QPointF(6.2, 6.3), QPointF(11.8, 6.3))
        painter.drawLine(QPointF(6.2, 9.0), QPointF(11.8, 9.0))
        painter.drawLine(QPointF(6.2, 11.7), QPointF(10.0, 11.7))

    painter.end()
    return pixmap


def make_icon(kind: str, color: str, active_color: str | None = None, size: int = 18) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_paint_icon(kind, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(
        _paint_icon(kind, active_color or color, size),
        QIcon.Mode.Active,
        QIcon.State.Off,
    )
    return icon


# -----------------------------------------------------------------------------
# Stable worker: the business flow is intentionally identical to the working UI
# -----------------------------------------------------------------------------

class ProcessingThread(QThread):
    progress_changed = Signal(int, str)
    media_info_ready = Signal(dict)
    result_ready = Signal(str)
    failed = Signal(str)

    def __init__(
            self,
            *,
            url: str,
            local_file: str,
            api_key: str,
            model: str,
            cookie_file: str,
            keep_download: bool,
            latest_log: Path,
            parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.local_file = local_file
        self.api_key = api_key
        self.model = model
        self.cookie_file = cookie_file
        self.keep_download = keep_download
        self.latest_log = latest_log

    def _progress(self, percent: int, text: str) -> None:
        self.progress_changed.emit(percent, text)

    def _write_log(self, line: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with self.latest_log.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line.rstrip() + "\n")

    def run(self) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="bili_summarizer_") as temp:
                temp_dir = Path(temp)

                if self.url:
                    source = download_bilibili_audio(
                        url=self.url,
                        output_dir=temp_dir / "download",
                        cookie_file=self.cookie_file,
                        progress=self._progress,
                        log=self._write_log,
                        keep_dir=DOWNLOAD_DIR if self.keep_download else None,
                    )
                    audio = normalize_audio(
                        source,
                        temp_dir / "prepared",
                        self._progress,
                        self._write_log,
                    )
                else:
                    audio = normalize_audio(
                        self.local_file,
                        temp_dir / "prepared",
                        self._progress,
                        self._write_log,
                    )

                # Extra UI metadata only; does not alter the stable processing flow.
                try:
                    source_path = Path(source) if self.url else Path(self.local_file)
                    source_size = source_path.stat().st_size if source_path.is_file() else 0
                    prepared_path = Path(audio)
                    prepared_size = prepared_path.stat().st_size if prepared_path.is_file() else 0
                    self.media_info_ready.emit(
                        {
                            "source_name": source_path.name,
                            "source_bytes": int(source_size),
                            "prepared_bytes": int(prepared_size),
                        }
                    )
                except Exception:
                    # UI metadata must never affect summarization.
                    pass

                result = summarize_audio(
                    audio_path=audio,
                    api_key=self.api_key,
                    model=self.model,
                    progress=self._progress,
                )

            self.result_ready.emit(result)
        except (MediaError, GeminiError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self._write_log(f"[unexpected] {type(exc).__name__}: {exc}")
            self.failed.emit(f"未预期错误：{exc}")


class ModelRefreshThread(QThread):
    models_ready = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key

    def run(self) -> None:
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key.strip())
            names: list[str] = []

            for model in client.models.list():
                name = str(getattr(model, "name", "") or "").strip()
                actions = getattr(model, "supported_actions", None) or []
                actions_normalized = {
                    str(action).replace("_", "").lower() for action in actions
                }
                if "generatecontent" not in actions_normalized:
                    continue
                if name.startswith("models/"):
                    name = name[7:]
                if name.startswith("gemini-"):
                    names.append(name)

            names = sorted(set(names))
            if not names:
                raise RuntimeError("当前 API Key 没有查询到可用于 generateContent 的 Gemini 模型。")
            self.models_ready.emit(names)
        except Exception as exc:
            self.failed.emit(str(exc))


# -----------------------------------------------------------------------------
# Reusable UI widgets
# -----------------------------------------------------------------------------

class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isChecked():
            track = QColor("#4F7DF3")
            knob_x = 18
        else:
            track = QColor("#8B93A1")
            knob_x = 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 11, 11)

        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob_x, 3, 16, 16)


class ThemeToggle(QAbstractButton):
    """Animated light / dark theme switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(56, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("切换深色 / 浅色模式")

        # 0.0 = light/left, 1.0 = dark/right.
        self._position = 0.0
        self._position_animation = QPropertyAnimation(self, b"position", self)
        self._position_animation.setDuration(180)
        self._position_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_position)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_position(self, checked: bool) -> None:
        self._position_animation.stop()
        self._position_animation.setStartValue(self._position)
        self._position_animation.setEndValue(1.0 if checked else 0.0)
        self._position_animation.start()

    def set_position_immediate(self, value: float) -> None:
        """Synchronize the knob without animation, useful during startup."""
        self._position_animation.stop()
        self._set_position(value)

    @staticmethod
    def _mix_color(a: str, b: str, t: float) -> QColor:
        ca = QColor(a)
        cb = QColor(b)
        t = max(0.0, min(1.0, t))
        return QColor(
            round(ca.red() + (cb.red() - ca.red()) * t),
            round(ca.green() + (cb.green() - ca.green()) * t),
            round(ca.blue() + (cb.blue() - ca.blue()) * t),
            round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
        )

    def _draw_sun(self, painter: QPainter, cx: float, cy: float, opacity: float) -> None:
        if opacity <= 0.001:
            return
        painter.save()
        painter.setOpacity(opacity)
        painter.setPen(
            QPen(
                QColor("#F4A62A"),
                1.7,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))
        rays = [
            ((0, -8), (0, -6)), ((0, 8), (0, 6)),
            ((-8, 0), (-6, 0)), ((8, 0), (6, 0)),
            ((-5.7, -5.7), (-4.3, -4.3)), ((5.7, 5.7), (4.3, 4.3)),
            ((5.7, -5.7), (4.3, -4.3)), ((-5.7, 5.7), (-4.3, 4.3)),
        ]
        for start, end in rays:
            painter.drawLine(
                QPointF(cx + start[0], cy + start[1]),
                QPointF(cx + end[0], cy + end[1]),
            )
        painter.restore()

    def _draw_moon(self, painter: QPainter, cx: float, cy: float, opacity: float) -> None:
        if opacity <= 0.001:
            return
        painter.save()
        painter.setOpacity(opacity)
        moon = QPainterPath()
        moon.addEllipse(QRectF(cx - 6, cy - 6, 12, 12))
        cut = QPainterPath()
        cut.addEllipse(QRectF(cx - 2, cy - 7, 11, 11))
        painter.fillPath(moon.subtracted(cut), QColor("#FFD166"))
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = self._position

        # The switch itself also blends its colors while the knob is moving.
        track_color = self._mix_color("#EEF2FA", "#252A35", t)
        border_color = self._mix_color("#DDE3EE", "#353C49", t)
        knob_color = self._mix_color("#FFFFFF", "#343B49", t)

        track_rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, 16, 16)

        knob_size = 26
        knob_x = 3 + (self.width() - knob_size - 6) * t
        knob_rect = QRectF(knob_x, 3, knob_size, knob_size)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)

        cx = knob_rect.center().x()
        cy = knob_rect.center().y()

        # Cross-fade sun/moon while the knob glides across the track.
        self._draw_sun(painter, cx, cy, 1.0 - t)
        self._draw_moon(painter, cx, cy, t)
        painter.end()


class ThemeFadeOverlay(QWidget):
    """Paint-only snapshot overlay used for a stable theme cross-fade.

    Using a QWidget that paints the cached pixmap itself avoids the extra
    QGraphicsOpacityEffect composition pass.  That combination can visibly
    "jump" for frameless translucent windows with drop shadows on Windows.
    The overlay is never inserted into a layout, so it cannot influence any
    widget geometry while the theme stylesheet is being replaced.
    """

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._fade_opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _get_fade_opacity(self) -> float:
        return self._fade_opacity

    def _set_fade_opacity(self, value: float) -> None:
        self._fade_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    fadeOpacity = Property(float, _get_fade_opacity, _set_fade_opacity)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setOpacity(self._fade_opacity)
        # QWidget.grab() returns a DPR-aware pixmap. Drawing it into the exact
        # logical widget rect keeps the snapshot aligned on HiDPI displays.
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()


class SmoothProgressBar(QWidget):
    """Self-painted determinate / indeterminate progress bar.

    The whole track is repainted on every frame instead of moving a child
    widget with setGeometry(). This avoids stale-pixel trails on frameless,
    translucent Windows windows.
    """

    def __init__(
        self,
        parent=None,
        *,
        bar_height: int = 7,
        segment_ratio: float = 0.22,
        min_segment: float = 48.0,
        track_kind: str = "soft",
    ):
        super().__init__(parent)
        self._display_progress = 0.0
        self._phase = 0.0
        self._indeterminate = False
        self._segment_ratio = float(segment_ratio)
        self._min_segment = float(min_segment)
        self._track_kind = str(track_kind)

        self.setFixedHeight(int(bar_height))
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._progress_animation = QPropertyAnimation(
            self,
            b"displayProgress",
            self,
        )
        self._progress_animation.setDuration(300)
        self._progress_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

    def _get_display_progress(self) -> float:
        return self._display_progress

    def _set_display_progress(self, value: float) -> None:
        self._display_progress = max(0.0, min(100.0, float(value)))
        self.update()

    displayProgress = Property(
        float,
        _get_display_progress,
        _set_display_progress,
    )

    def set_progress(self, value: float, *, animate: bool = True) -> None:
        value = max(0.0, min(100.0, float(value)))
        self._indeterminate = False
        self._progress_animation.stop()

        if not animate:
            self._set_display_progress(value)
            return

        if abs(self._display_progress - value) < 0.01:
            self.update()
            return

        self._progress_animation.setStartValue(self._display_progress)
        self._progress_animation.setEndValue(value)
        self._progress_animation.start()

    def set_indeterminate(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._indeterminate == enabled:
            return
        self._indeterminate = enabled
        if enabled:
            self._progress_animation.stop()
        self.update()

    def set_phase(self, value: float) -> None:
        self._phase = max(0.0, min(1.0, float(value)))
        self.update()

    def _track_color(self) -> QColor:
        dark = getattr(self.window(), "theme", "light") == "dark"
        if self._track_kind == "border":
            return QColor("#2A303A" if dark else "#E1E5EC")
        return QColor("#202631" if dark else "#F1F4FA")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = float(self.width())
        height = float(self.height())
        if width <= 0.0 or height <= 0.0:
            painter.end()
            return

        track_rect = QRectF(0.0, 0.0, width, height)
        radius = height / 2.0

        # Paint the entire track first. Any pixels from the previous moving
        # segment are overwritten before the new segment is drawn.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track_color())
        painter.drawRoundedRect(track_rect, radius, radius)

        painter.setBrush(QColor("#4F7DF3"))

        if self._indeterminate:
            import math
            ratio = 0.5 - 0.5 * math.cos(2.0 * math.pi * self._phase)
            segment = min(
                width,
                max(self._min_segment, width * self._segment_ratio),
            )
            travel = max(0.0, width - segment)
            x = travel * ratio
            fill_rect = QRectF(x, 0.0, segment, height)
        else:
            fill_width = width * self._display_progress / 100.0
            if fill_width <= 0.01:
                painter.end()
                return
            fill_rect = QRectF(0.0, 0.0, fill_width, height)

        fill_radius = min(radius, fill_rect.width() / 2.0)
        painter.drawRoundedRect(fill_rect, fill_radius, fill_radius)
        painter.end()


class StatusPill(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("statusPill")
        self.setFixedHeight(36)

        # 胶囊只占自身内容需要的空间，不参与横向拉伸
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        self.dot = QLabel(self)
        self.dot.setObjectName("statusDot")
        self.dot.setFixedSize(7, 7)
        layout.addWidget(self.dot)

        self.label = QLabel("就绪", self)
        self.label.setObjectName("statusText")
        self.label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.label)

        self._update_width()

    def _update_width(self):
        text_width = self.label.fontMetrics().horizontalAdvance(
            self.label.text()
        )

        # 左右边距 28
        # 圆点 7
        # spacing 8
        # 再留一点余量
        width = 28 + 7 + 8 + text_width + 4

        # 最小保持比较协调
        width = max(88, width)

        self.setFixedWidth(width)

    def set_status(self, text: str, error: bool = False) -> None:
        # 不再强制截断文字
        self.label.setText(text)

        self.setToolTip(text)

        self.dot.setProperty("error", error)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

        # 状态文字改变后重新计算胶囊宽度
        self._update_width()


class DragArea(QWidget):
    """Area that delegates moving/maximizing to Qt's native window APIs."""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle and not window.isMaximized():
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    def __init__(self, edges: Qt.Edge, cursor: Qt.CursorShape, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if not window.isMaximized() and window.windowHandle():
                window.windowHandle().startSystemResize(self.edges)
                event.accept()
                return
        super().mousePressEvent(event)


class DropCard(QFrame):
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropCard")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                suffix = Path(urls[0].toLocalFile()).suffix.lower()
                if suffix in SUPPORTED_MEDIA:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()
        else:
            event.ignore()


class LogWindow(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("yt-dlp 下载日志")
        self.resize(920, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        box = QTextEdit(self)
        box.setReadOnly(True)
        box.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        box.setFont(QFont(APP_FONT_FAMILY, 10))
        box.setPlainText(text)
        layout.addWidget(box)


# -----------------------------------------------------------------------------
# Main window
# -----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("B站视频总结工具")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1320, 860)
        self.setMinimumSize(1040, 700)
        self.setAcceptDrops(False)

        self.settings = load_settings()
        self.api_key = load_api_key()
        self.local_file = ""
        self.result_markdown = ""
        self.processing_thread: ProcessingThread | None = None
        self.model_thread: ModelRefreshThread | None = None
        self.latest_log = LOG_DIR / "latest_yt_dlp.log"
        self.qt_settings = QSettings(APP_ORG, APP_NAME)
        self.theme = self._load_theme()
        self.log_window: LogWindow | None = None
        self.current_progress = 0

        # =============================
        # Result / focus UI state
        # =============================

        self.result_mode = False
        self.task_details_expanded = False
        self.focus_mode = False

        # ==========================================
        # Live processing feedback / Gemini activity
        # ==========================================
        self.activity_running = False
        self.activity_stage = "idle"
        self.activity_stage_started = 0.0
        self.activity_task_started = 0.0
        self.activity_inference_started = 0.0
        self.activity_stage_durations: dict[str, float] = {}
        self.activity_tick_count = 0
        self.activity_pulse_bright = False
        self.indeterminate_mode = False
        self.indeterminate_phase = 0.0
        self.activity_source_kind = "video"
        self.activity_source_desc = ""
        self.activity_model_desc = ""
        self.activity_failed_stage: str | None = None
        self.activity_media_info: dict[str, object] = {}
        self.activity_panel_expanded = False

        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(250)
        self.activity_timer.timeout.connect(self._tick_activity)

        # Smooth infinite movement used while Gemini inference has no real
        # percentage. A cosine trajectory gives zero velocity at both ends.
        self.indeterminate_animation = QVariantAnimation(self)
        self.indeterminate_animation.setStartValue(0.0)
        self.indeterminate_animation.setEndValue(1.0)
        self.indeterminate_animation.setDuration(1800)
        self.indeterminate_animation.setLoopCount(-1)
        self.indeterminate_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.indeterminate_animation.valueChanged.connect(
            self._on_indeterminate_phase
        )

        # Keep the theme cross-fade objects alive until their animation ends.
        # The overlay is a paint-only child of centralWidget(), never a layout item.
        self._theme_overlay: ThemeFadeOverlay | None = None
        self._theme_fade_animation: QPropertyAnimation | None = None

        self._build_shell()
        self._build_sidebar()
        self._build_content()
        self._build_resize_handles()
        self._refresh_config_labels()
        self._apply_theme()
        self._update_maximize_icon()

        self.focus_shortcut = QShortcut(
            QKeySequence("Escape"),
            self,
        )

        self.focus_shortcut.activated.connect(
            self._escape_focus_mode
        )

    # ------------------------------------------------------------------
    # Window shell
    # ------------------------------------------------------------------

    def _build_shell(self) -> None:
        central = QWidget(self)
        central.setObjectName("transparentRoot")
        self.setCentralWidget(central)

        self.outer_layout = QVBoxLayout(central)
        self.outer_layout.setContentsMargins(9, 9, 9, 9)
        self.outer_layout.setSpacing(0)

        self.frame = QFrame(central)
        self.frame.setObjectName("windowFrame")
        self.outer_layout.addWidget(self.frame)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(28)
        self.shadow.setOffset(0, 4)
        self.shadow.setColor(QColor(0, 0, 0, 85))
        self.frame.setGraphicsEffect(self.shadow)

        shell = QHBoxLayout(self.frame)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame(self.frame)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(268)
        shell.addWidget(self.sidebar)

        self.main_panel = QFrame(self.frame)
        self.main_panel.setObjectName("mainPanel")
        shell.addWidget(self.main_panel, 1)

    def _window_button(self, kind: str) -> QPushButton:
        button = QPushButton(self)
        button.setObjectName("windowButtonClose" if kind == "close" else "windowButton")
        button.setProperty("windowKind", kind)
        button.setFixedSize(46, 40)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFlat(True)
        button.setIconSize(QSize(18, 18))

        if kind == "min":
            self.min_button = button
            button.clicked.connect(self.showMinimized)
        elif kind == "max":
            self.max_button = button
            button.clicked.connect(self._toggle_maximize)
        else:
            self.close_button = button
            button.clicked.connect(self.close)
        return button

    def _build_resize_handles(self) -> None:
        self.resize_handles: list[ResizeHandle] = []
        specs = [
            (Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            (Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeFDiagCursor),
            (Qt.Edge.TopEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeBDiagCursor),
            (Qt.Edge.BottomEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeFDiagCursor),
        ]
        for edges, cursor in specs:
            handle = ResizeHandle(edges, cursor, self)
            handle.raise_()
            self.resize_handles.append(handle)
        self._position_resize_handles()

    def _position_resize_handles(self) -> None:
        if not self.resize_handles:
            return
        if self.isMaximized():
            for handle in self.resize_handles:
                handle.hide()
            return

        for handle in self.resize_handles:
            handle.show()

        w, h, t, c = self.width(), self.height(), 7, 14
        left, right, top, bottom, tl, tr, bl, br = self.resize_handles
        left.setGeometry(0, c, t, max(0, h - 2 * c))
        right.setGeometry(w - t, c, t, max(0, h - 2 * c))
        top.setGeometry(c, 0, max(0, w - 2 * c), t)
        bottom.setGeometry(c, h - t, max(0, w - 2 * c), t)
        tl.setGeometry(0, 0, c, c)
        tr.setGeometry(w - c, 0, c, c)
        bl.setGeometry(0, h - c, c, c)
        br.setGeometry(w - c, h - c, c, c)
        for handle in self.resize_handles:
            handle.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_resize_handles()
        if hasattr(self, "progress_bar"):
            self.progress_bar.update()
        if self._theme_overlay is not None and self.centralWidget() is not None:
            self._theme_overlay.setGeometry(self.centralWidget().rect())
        if getattr(self, "activity_panel_expanded", False):
            self._position_activity_panel()
        if hasattr(self, "activity_wait_bar"):
            self.activity_wait_bar.update()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_maximize_icon()
            if self.isMaximized():
                self.outer_layout.setContentsMargins(0, 0, 0, 0)
                self.shadow.setEnabled(False)
            else:
                self.outer_layout.setContentsMargins(9, 9, 9, 9)
                self.shadow.setEnabled(True)
            self._apply_theme()
            self._position_resize_handles()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _update_maximize_icon(self) -> None:
        if hasattr(self, "max_button"):
            self._update_ui_icons()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self) -> None:
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(22, 18, 18, 18)
        layout.setSpacing(12)

        brand = DragArea(self.sidebar)
        brand.setFixedHeight(94)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(2, 8, 0, 14)
        brand_layout.setSpacing(12)

        logo = QLabel("✦", brand)
        logo.setObjectName("brandLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(46, 46)
        brand_layout.addWidget(logo)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        title = QLabel("BiliSummary", brand)
        title.setObjectName("brandTitle")
        subtitle = QLabel("AI 视频笔记助手", brand)
        subtitle.setObjectName("mutedText")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_layout.addLayout(brand_text, 1)
        layout.addWidget(brand)

        layout.addWidget(self._section_label("连接状态"))
        connection_card = QFrame(self.sidebar)
        connection_card.setObjectName("sideCard")
        conn = QVBoxLayout(connection_card)
        conn.setContentsMargins(16, 14, 16, 14)
        conn.setSpacing(9)
        self.api_status = QLabel(connection_card)
        self.api_status.setObjectName("statusGood")
        self.cookie_status = QLabel(connection_card)
        self.cookie_status.setObjectName("mutedText")
        conn.addWidget(self.api_status)
        conn.addWidget(self.cookie_status)
        layout.addWidget(connection_card)

        layout.addWidget(self._section_label("AI 模型"))
        model_row = QHBoxLayout()
        model_row.setSpacing(7)
        self.model_combo = QComboBox(self.sidebar)
        self.model_combo.setObjectName("modelCombo")
        self.model_combo.setMinimumHeight(42)
        model_values = list(FALLBACK_MODELS)
        if self.settings.model not in model_values:
            model_values.insert(0, self.settings.model)
        self.model_combo.addItems(model_values)
        self.model_combo.setCurrentText(self.settings.model)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        model_row.addWidget(self.model_combo, 1)

        self.refresh_models_button = QPushButton("", self.sidebar)
        self.refresh_models_button.setObjectName("iconButton")
        self.refresh_models_button.setFixedSize(42, 42)
        self.refresh_models_button.setToolTip("根据当前 API Key 刷新可用模型")
        self.refresh_models_button.clicked.connect(self.refresh_models)
        model_row.addWidget(self.refresh_models_button)
        layout.addLayout(model_row)

        keep_card = QFrame(self.sidebar)
        keep_card.setObjectName("sideCard")
        keep_layout = QVBoxLayout(keep_card)
        keep_layout.setContentsMargins(14, 13, 14, 13)
        keep_layout.setSpacing(10)
        switch_row = QHBoxLayout()
        self.keep_switch = ToggleSwitch(keep_card)
        self.keep_switch.setChecked(bool(self.settings.keep_download))
        self.keep_switch.toggled.connect(self._keep_download_changed)
        switch_row.addWidget(self.keep_switch)
        switch_row.addWidget(QLabel("保留下载音频", keep_card), 1)
        keep_layout.addLayout(switch_row)
        open_downloads = QPushButton("打开下载目录", keep_card)
        open_downloads.setObjectName("linkButton")
        open_downloads.clicked.connect(self.open_download_dir)
        keep_layout.addWidget(open_downloads, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(keep_card)

        layout.addWidget(self._section_label("设置"))

        self.api_button = QPushButton("🔑   API Key", self.sidebar)
        api_button = self.api_button
        api_button.setObjectName("sidebarAction")
        api_button.clicked.connect(self.set_api_key)
        layout.addWidget(api_button)

        self.cookie_button = QPushButton("🍪   Cookie", self.sidebar)
        cookie_button = self.cookie_button
        cookie_button.setObjectName("sidebarAction")
        cookie_button.clicked.connect(self.set_cookie)
        layout.addWidget(cookie_button)

        self.log_button = QPushButton("📜   下载日志", self.sidebar)
        log_button = self.log_button
        log_button.setObjectName("sidebarAction")
        log_button.clicked.connect(self.show_log)
        layout.addWidget(log_button)

        # ===== 彩色 Emoji 字体 =====
        emoji_font = QFont()
        emoji_font.setFamilies([
            APP_FONT_FAMILY,
            APP_EMOJI_FAMILY,
        ])
        emoji_font.setPointSize(11)

        self.api_button.setFont(emoji_font)
        self.cookie_button.setFont(emoji_font)
        self.log_button.setFont(emoji_font)

        layout.addStretch(1)
        version = QLabel("PySide6 UI · 稳定流程", self.sidebar)
        version.setObjectName("mutedText")
        layout.addWidget(version)
        pipeline = QLabel("yt-dlp  →  FFmpeg  →  Gemini", self.sidebar)
        pipeline.setObjectName("monoMuted")
        layout.addWidget(pipeline)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text, self.sidebar)
        label.setObjectName("sectionLabel")
        return label

    # ------------------------------------------------------------------
    # Main content
    # ------------------------------------------------------------------

    def _build_content(self) -> None:
        self.main_layout = QVBoxLayout(self.main_panel)
        main = self.main_layout

        main.setContentsMargins(28, 0, 24, 24)
        main.setSpacing(16)

        # Caption row: only native-style window controls live here.
        caption = DragArea(self.main_panel)
        caption.setFixedHeight(42)
        caption_layout = QHBoxLayout(caption)
        caption_layout.setContentsMargins(0, 0, 0, 0)
        caption_layout.setSpacing(0)
        caption_layout.addStretch(1)

        # =====================================
        # 全局主题切换
        # =====================================

        self.theme_toggle = ThemeToggle(caption)

        self.theme_toggle.setChecked(
            self.theme == "dark"
        )
        self.theme_toggle.set_position_immediate(
            1.0 if self.theme == "dark" else 0.0
        )

        self.theme_toggle.clicked.connect(
            self.toggle_theme
        )

        self.theme_toggle.setToolTip(
            "切换到浅色模式"
            if self.theme == "dark"
            else "切换到深色模式"
        )

        caption_layout.addWidget(
            self.theme_toggle,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        # 与窗口控制按钮稍微留一点距离
        caption_layout.addSpacing(10)

        # Windows 风格窗口控制
        caption_layout.addWidget(self._window_button("min"))
        caption_layout.addWidget(self._window_button("max"))
        caption_layout.addWidget(self._window_button("close"))

        main.addWidget(caption)

        # Page heading is a separate row so the status pill never competes
        # with the caption buttons for vertical alignment.
        self.page_header = DragArea(self.main_panel)
        header = self.page_header

        header.setFixedHeight(84)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 8, 12)
        header_layout.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        page_title = QLabel("视频摘要", header)
        page_title.setObjectName("pageTitle")
        page_subtitle = QLabel("粘贴 B 站链接，或拖入本地音视频，让 Gemini 提炼核心内容。", header)
        page_subtitle.setObjectName("mutedText")
        title_box.addWidget(page_title)
        title_box.addWidget(page_subtitle)

        header_layout.addLayout(title_box, 1)

        # 状态胶囊
        self.status_pill = StatusPill(header)

        header_layout.addWidget(
            self.status_pill,
            alignment=(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
            ),
        )
        main.addWidget(header)
        # ==================================================
        # Collapsed task summary bar
        # 总结完成后替代输入区 + 进度区
        # ==================================================

        self.task_compact_bar = QFrame(self.main_panel)
        self.task_compact_bar.setObjectName("compactBar")
        self.task_compact_bar.setFixedHeight(48)

        compact_layout = QHBoxLayout(self.task_compact_bar)
        compact_layout.setContentsMargins(16, 0, 16, 0)
        compact_layout.setSpacing(12)

        self.task_toggle_button = QPushButton(
            "▶  视频与任务信息",
            self.task_compact_bar,
        )
        self.task_toggle_button.setObjectName("compactToggleButton")
        self.task_toggle_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.task_toggle_button.clicked.connect(
            self.toggle_task_details
        )

        compact_layout.addWidget(self.task_toggle_button)

        compact_layout.addStretch(1)

        self.task_summary_label = QLabel(
            "总结完成 · 100%",
            self.task_compact_bar,
        )
        self.task_summary_label.setObjectName("mutedText")

        compact_layout.addWidget(self.task_summary_label)

        # 初始状态不显示
        self.task_compact_bar.hide()

        main.addWidget(self.task_compact_bar)

        self.input_card = QFrame(self.main_panel)
        input_card = self.input_card

        input_card.setObjectName("card")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(20, 18, 20, 20)
        input_layout.setSpacing(12)

        input_header = QHBoxLayout()
        input_title = QLabel("输入视频", input_card)
        input_title.setObjectName("cardTitle")
        input_header.addWidget(input_title)
        input_header.addStretch(1)
        clear_button = QPushButton("清空", input_card)
        clear_button.setObjectName("linkButton")
        clear_button.clicked.connect(self.clear_inputs)
        input_header.addWidget(clear_button)
        input_layout.addLayout(input_header)

        url_row = QHBoxLayout()
        url_row.setSpacing(9)
        self.url_edit = QLineEdit(input_card)
        self.url_edit.setObjectName("urlEdit")
        self.url_edit.setPlaceholderText("粘贴 B 站视频链接，例如 https://www.bilibili.com/video/BV...")
        self.url_edit.setMinimumHeight(48)
        self.url_edit.textEdited.connect(self._url_edited)
        url_row.addWidget(self.url_edit, 1)
        paste_button = QPushButton("粘贴", input_card)
        paste_button.setObjectName("secondaryButton")
        paste_button.setFixedSize(78, 48)
        paste_button.clicked.connect(self.paste_url)
        url_row.addWidget(paste_button)
        input_layout.addLayout(url_row)

        self.drop_card = DropCard(input_card)
        self.drop_card.setMinimumHeight(88)
        self.drop_card.file_dropped.connect(self._set_local_file)
        drop_layout = QHBoxLayout(self.drop_card)
        drop_layout.setContentsMargins(16, 12, 16, 12)
        drop_layout.setSpacing(12)

        plus = QLabel("＋", self.drop_card)
        plus.setObjectName("dropIcon")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setFixedSize(48, 48)
        drop_layout.addWidget(plus)

        file_text = QVBoxLayout()
        file_text.setSpacing(3)
        self.file_name_label = QLabel("拖入本地音视频文件", self.drop_card)
        self.file_name_label.setObjectName("fileTitle")
        self.file_path_label = QLabel("支持 m4s / mp3 / mp4 / m4a / wav 等常见格式", self.drop_card)
        self.file_path_label.setObjectName("mutedText")
        self.file_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_text.addWidget(self.file_name_label)
        file_text.addWidget(self.file_path_label)
        drop_layout.addLayout(file_text, 1)

        choose_button = QPushButton("选择文件", self.drop_card)
        choose_button.setObjectName("secondaryButton")
        choose_button.setFixedSize(96, 42)
        choose_button.clicked.connect(self.choose_file)
        drop_layout.addWidget(choose_button)
        input_layout.addWidget(self.drop_card)
        main.addWidget(input_card)

        self.progress_card = QFrame(self.main_panel)
        progress_card = self.progress_card

        progress_card.setObjectName("card")

        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(20, 18, 20, 16)
        progress_layout.setSpacing(11)

        self.start_button = QPushButton("开始总结", progress_card)
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumHeight(52)
        self.start_button.clicked.connect(self.start_processing)
        progress_layout.addWidget(self.start_button)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(12)
        self.progress_bar = SmoothProgressBar(
            progress_card,
            bar_height=7,
            segment_ratio=0.22,
            min_segment=48.0,
            track_kind="soft",
        )
        bar_row.addWidget(self.progress_bar, 1)
        self.percent_label = QLabel("0%", progress_card)
        self.percent_label.setObjectName("monoMuted")
        self.percent_label.setFixedWidth(68)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.percent_label)
        progress_layout.addLayout(bar_row)

        # Main status line + optional detailed task-status dropdown.
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self.progress_text = QLabel("就绪", progress_card)
        self.progress_text.setObjectName("mutedText")
        self.progress_text.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        status_row.addWidget(self.progress_text, 1)

        self.activity_toggle_button = QPushButton("查看任务状态  ▾", progress_card)
        self.activity_toggle_button.setObjectName("activityToggleButton")
        self.activity_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activity_toggle_button.setFixedHeight(30)
        self.activity_toggle_button.setToolTip("展开下载、音频处理、Gemini 上传与 AI 推理的详细状态")
        self.activity_toggle_button.clicked.connect(self.toggle_activity_panel)
        status_row.addWidget(self.activity_toggle_button)

        progress_layout.addLayout(status_row)

        # ==================================================
        # On-demand task status panel
        # Hidden by default; users expand it only when needed.
        # ==================================================
        # Floating on-demand telemetry popup.  It is intentionally NOT part of
        # progress_layout, otherwise expanding it forces the whole page to
        # compress vertically and the stage rows become crowded.
        self.activity_panel = QFrame(self.main_panel)
        self.activity_panel.setObjectName("aiActivityPanel")
        self.activity_panel.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self.activity_panel_shadow = QGraphicsDropShadowEffect(self.activity_panel)
        self.activity_panel_shadow.setBlurRadius(30)
        self.activity_panel_shadow.setOffset(0, 8)
        self.activity_panel_shadow.setColor(QColor(0, 0, 0, 65))
        self.activity_panel.setGraphicsEffect(self.activity_panel_shadow)

        activity_layout = QVBoxLayout(self.activity_panel)
        activity_layout.setContentsMargins(22, 20, 22, 18)
        activity_layout.setSpacing(16)

        # Header
        activity_header = QHBoxLayout()
        activity_header.setSpacing(9)

        self.activity_pulse = QLabel("●", self.activity_panel)
        self.activity_pulse.setObjectName("activityPulse")
        self.activity_pulse.setFixedSize(18, 18)
        self.activity_pulse.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        activity_header.addWidget(self.activity_pulse)

        self.activity_title = QLabel("任务状态", self.activity_panel)
        self.activity_title.setObjectName("activityTitle")
        activity_header.addWidget(self.activity_title)
        activity_header.addStretch(1)

        self.activity_elapsed_label = QLabel("总耗时 00:00", self.activity_panel)
        self.activity_elapsed_label.setObjectName("activityElapsed")
        self.activity_elapsed_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        activity_header.addWidget(self.activity_elapsed_label)

        self.activity_close_button = QPushButton("收起", self.activity_panel)
        self.activity_close_button.setObjectName("activityPanelCloseButton")
        self.activity_close_button.setFixedHeight(28)
        self.activity_close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activity_close_button.clicked.connect(self.toggle_activity_panel)
        activity_header.addWidget(self.activity_close_button)

        activity_layout.addLayout(activity_header)

        # Metadata summary: three balanced columns with dedicated label/value
        # rows.  This uses horizontal space instead of consuming vertical space.
        meta_grid = QGridLayout()
        meta_grid.setContentsMargins(0, 2, 0, 2)
        meta_grid.setHorizontalSpacing(24)
        meta_grid.setVerticalSpacing(5)
        for column in range(3):
            meta_grid.setColumnStretch(column, 1)

        model_key = QLabel("模型", self.activity_panel)
        model_key.setObjectName("activityMetaKey")
        self.activity_model_value = QLabel("—", self.activity_panel)
        self.activity_model_value.setObjectName("activityMetaValue")
        self.activity_model_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.activity_model_value.setMinimumHeight(24)

        source_key = QLabel("来源", self.activity_panel)
        source_key.setObjectName("activityMetaKey")
        self.activity_source_value = QLabel("—", self.activity_panel)
        self.activity_source_value.setObjectName("activityMetaValue")
        self.activity_source_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.activity_source_value.setWordWrap(True)
        self.activity_source_value.setMinimumHeight(24)

        audio_key = QLabel("Gemini 音频", self.activity_panel)
        audio_key.setObjectName("activityMetaKey")
        self.activity_audio_value = QLabel("—", self.activity_panel)
        self.activity_audio_value.setObjectName("activityMetaValue")
        self.activity_audio_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.activity_audio_value.setMinimumHeight(24)

        meta_grid.addWidget(model_key, 0, 0)
        meta_grid.addWidget(source_key, 0, 1)
        meta_grid.addWidget(audio_key, 0, 2)
        meta_grid.addWidget(self.activity_model_value, 1, 0)
        meta_grid.addWidget(self.activity_source_value, 1, 1)
        meta_grid.addWidget(self.activity_audio_value, 1, 2)
        activity_layout.addLayout(meta_grid)

        section_title = QLabel("任务阶段", self.activity_panel)
        section_title.setObjectName("activitySectionTitle")
        activity_layout.addWidget(section_title)

        stage_grid = QGridLayout()
        stage_grid.setContentsMargins(0, 0, 0, 0)
        stage_grid.setHorizontalSpacing(10)
        stage_grid.setVerticalSpacing(7)
        stage_grid.setColumnStretch(1, 1)

        self.activity_stage_icon_labels = {}
        self.activity_stage_name_labels = {}
        self.activity_stage_time_labels = {}

        stage_defs = [
            ("source", "获取 B站音频"),
            ("normalize", "音频预处理"),
            ("upload", "上传 / 处理 Gemini 音频"),
            ("inference", "AI 生成结构化摘要"),
        ]

        for row, (key, label_text) in enumerate(stage_defs):
            icon_label = QLabel("○", self.activity_panel)
            icon_label.setObjectName("activityStageIcon")
            icon_label.setFixedWidth(18)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name_label = QLabel(label_text, self.activity_panel)
            name_label.setObjectName("activityStageName")

            time_label = QLabel("等待", self.activity_panel)
            time_label.setObjectName("activityStageTime")
            icon_label.setMinimumHeight(28)
            name_label.setMinimumHeight(28)
            time_label.setMinimumWidth(88)
            time_label.setMinimumHeight(28)
            time_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            self.activity_stage_icon_labels[key] = icon_label
            self.activity_stage_name_labels[key] = name_label
            self.activity_stage_time_labels[key] = time_label

            stage_grid.addWidget(icon_label, row, 0)
            stage_grid.addWidget(name_label, row, 1)
            stage_grid.addWidget(time_label, row, 2)
            stage_grid.setRowMinimumHeight(row, 30)

        activity_layout.addLayout(stage_grid)

        self.activity_wait_bar = SmoothProgressBar(
            self.activity_panel,
            bar_height=5,
            segment_ratio=0.24,
            min_segment=40.0,
            track_kind="border",
        )
        activity_layout.addWidget(self.activity_wait_bar)

        self.activity_hint_label = QLabel(
            "详细状态会持续更新；收起此面板不会影响任务运行。",
            self.activity_panel,
        )
        self.activity_hint_label.setObjectName("activityHint")
        self.activity_hint_label.setWordWrap(True)
        self.activity_hint_label.setMinimumHeight(34)
        activity_layout.addWidget(self.activity_hint_label)

        # Popup is positioned manually over the main panel, so opening it does
        # not resize input/progress/result cards.
        self.activity_panel.hide()

        main.addWidget(progress_card)

        self.result_card = QFrame(self.main_panel)
        result_card = self.result_card

        result_card.setObjectName("card")

        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(20, 16, 20, 18)
        result_layout.setSpacing(10)

        result_header = QHBoxLayout()
        result_title = QLabel("总结结果", result_card)
        result_title.setObjectName("cardTitle")
        result_header.addWidget(result_title)
        result_header.addStretch(1)

        self.focus_button = QPushButton(
            "专注阅读",
            result_card,
        )

        self.focus_button.setObjectName(
            "secondaryButton"
        )

        self.focus_button.setEnabled(False)

        self.focus_button.setToolTip(
            "让总结内容占据整个工作区域"
        )

        self.focus_button.clicked.connect(
            self.toggle_focus_mode
        )

        result_header.addWidget(
            self.focus_button
        )

        self.copy_button = QPushButton("复制 Markdown", result_card)
        self.copy_button.setObjectName("secondaryButton")
        self.copy_button.clicked.connect(self.copy_result)
        self.copy_button.setEnabled(False)
        result_header.addWidget(self.copy_button)

        self.save_button = QPushButton("保存 Markdown", result_card)
        self.save_button.setObjectName("secondaryButton")
        self.save_button.clicked.connect(self.save_result)
        self.save_button.setEnabled(False)
        result_header.addWidget(self.save_button)
        result_layout.addLayout(result_header)

        self.result_browser = QTextBrowser(result_card)
        self.result_browser.setObjectName("resultBrowser")
        self.result_browser.setOpenExternalLinks(True)
        self.result_browser.setPlaceholderText(
            "总结完成后，结果会显示在这里。\n\n提示：详细的 yt-dlp 下载过程可在左侧“下载日志”中查看。"
        )
        result_layout.addWidget(self.result_browser, 1)
        main.addWidget(result_card, 1)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _load_theme(self) -> str:
        stored = str(self.qt_settings.value("theme", "") or "")
        if stored in {"light", "dark"}:
            return stored
        try:
            scheme = QGuiApplication.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "dark"

    def toggle_theme(self) -> None:
        self.theme = (
            "light"
            if self.theme == "dark"
            else "dark"
        )

        self.qt_settings.setValue(
            "theme",
            self.theme,
        )

        self._animate_theme_transition()

    def _clear_theme_overlay(self) -> None:
        if self._theme_fade_animation is not None:
            self._theme_fade_animation.stop()
            self._theme_fade_animation = None
        if self._theme_overlay is not None:
            self._theme_overlay.hide()
            self._theme_overlay.deleteLater()
            self._theme_overlay = None

    def _animate_theme_transition(self) -> None:
        """Switch themes without the one-frame shake seen on Windows.

        The previous version used a QLabel + QGraphicsOpacityEffect on top of a
        frameless translucent window that already contains a drop-shadow effect.
        On Windows that can force an extra off-screen composition pass and make
        the whole frame appear to jump for a frame.

        This version snapshots the *central widget* (including the frame and its
        shadow margins), paints that snapshot in a lightweight overlay, freezes
        visible updates while QSS is swapped, then fades only the cached pixels.
        No animation frame changes layout or reapplies the stylesheet.
        """
        self._clear_theme_overlay()

        root = self.centralWidget()
        if root is None or not root.isVisible():
            self._apply_theme()
            return

        # Snapshot the exact root coordinate system rather than self.frame.
        # self.frame has a QGraphicsDropShadowEffect; grabbing the frame itself
        # can produce a subtly different rasterized bound on Windows/HiDPI.
        snapshot = root.grab()
        if snapshot.isNull():
            self._apply_theme()
            return

        overlay = ThemeFadeOverlay(snapshot, root)
        overlay.setGeometry(root.rect())
        overlay.raise_()
        overlay.show()
        self._theme_overlay = overlay

        # Preserve result reading position because re-applying Markdown styles
        # can trigger a document relayout even though widget geometry is fixed.
        scroll_value = None
        if hasattr(self, "result_browser"):
            scroll_value = self.result_browser.verticalScrollBar().value()

        # QSS replacement can invalidate size hints for many descendants. Freeze
        # painting for that single operation so the intermediate relayout is never
        # exposed; the cached overlay remains the visible frame.
        root.setUpdatesEnabled(False)
        try:
            self._apply_theme()
            if scroll_value is not None:
                self.result_browser.verticalScrollBar().setValue(scroll_value)
        finally:
            root.setUpdatesEnabled(True)

        root.update()
        overlay.raise_()

        animation = QPropertyAnimation(overlay, b"fadeOpacity", overlay)
        animation.setDuration(300)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._theme_fade_animation = animation

        def cleanup() -> None:
            if self._theme_overlay is overlay:
                self._theme_overlay = None
            if self._theme_fade_animation is animation:
                self._theme_fade_animation = None
            overlay.hide()
            overlay.deleteLater()

        animation.finished.connect(cleanup)
        # Let Qt commit the newly styled backing widgets before the first fade
        # frame. This prevents a single blank/repaint frame on some Windows GPUs.
        QTimer.singleShot(0, animation.start)

    def _apply_theme(self) -> None:
        dark = self.theme == "dark"
        radius = 0 if self.isMaximized() else 14

        if dark:
            bg = "#0E1014"
            sidebar = "#14171D"
            card = "#181C23"
            input_bg = "#1E232C"
            border = "#2A303A"
            text = "#F2F4F8"
            muted = "#929CAA"
            hover = "#252B35"
            soft = "#202631"
            result_bg = "#1C212A"
        else:
            bg = "#F4F6FA"
            sidebar = "#FFFFFF"
            card = "#FFFFFF"
            input_bg = "#F7F8FB"
            border = "#E1E5EC"
            text = "#141820"
            muted = "#747E8C"
            hover = "#EEF1F6"
            soft = "#F1F4FA"
            result_bg = "#F8F9FB"

        accent = "#4F7DF3"
        accent_hover = "#416FE4"
        success = "#2FA572"

        self.frame.setStyleSheet(
            f"""
            QFrame#windowFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
            QFrame#sidebar {{
                background: {sidebar};
                border: none;
                border-top-left-radius: {radius}px;
                border-bottom-left-radius: {radius}px;
            }}
            QFrame#mainPanel {{
                background: {bg};
                border: none;
                border-top-right-radius: {radius}px;
                border-bottom-right-radius: {radius}px;
            }}
            QLabel {{ color: {text}; font-family: "Microsoft YaHei UI"; font-size: 12px; }}
            QLabel#mutedText {{ color: {muted}; font-size: 11px; }}
            QLabel#monoMuted {{ color: {muted}; font-family: "Microsoft YaHei UI"; font-size: 10px; }}
            QLabel#sectionLabel {{ color: {muted}; font-weight: 600; font-size: 11px; padding-top: 5px; }}
            QLabel#brandLogo {{ background: {accent}; color: white; border-radius: 12px; font-size: 22px; font-weight: 700; }}
            QLabel#brandTitle {{ font-size: 18px; font-weight: 700; }}
            QLabel#pageTitle {{ font-size: 27px; font-weight: 800; }}
            QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
            QLabel#fileTitle {{ font-size: 12px; font-weight: 650; }}
            QLabel#statusGood {{ color: {success}; font-weight: 650; }}
            QFrame#statusPill {{ background: {card}; border: 1px solid {border}; border-radius: 18px; }}
            QLabel#statusText {{ color: {muted}; font-size: 11px; }}
            QLabel#statusDot {{ background: {success}; border-radius: 3px; }}
            QLabel#statusDot[error="true"] {{ background: #D84A4A; }}
            QLabel#dropIcon {{ background: {soft}; color: {accent}; border-radius: 10px; font-size: 27px; }}
            QFrame#sideCard, QFrame#card {{
                background: {card};
                border: 1px solid {border};
                border-radius: 13px;
            }}
            QFrame#compactBar {{
                background: {card};
                border: 1px solid {border};
                border-radius: 11px;
            }}

            QPushButton#compactToggleButton {{
                background: transparent;
                color: {text};
                border: none;

                padding: 0;

                text-align: left;

                font-family: "Microsoft YaHei UI";
                font-size: 12px;
                font-weight: 650;
            }}

            QPushButton#compactToggleButton:hover {{
                color: {accent};
            }}
            QFrame#dropCard {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: 11px;
            }}
            QLineEdit#urlEdit {{
                background: {input_bg}; color: {text}; border: 1px solid {border};
                border-radius: 10px; padding: 0 13px; selection-background-color: {accent};
            }}
            QLineEdit#urlEdit:focus {{ border: 1px solid {accent}; }}
            QComboBox#modelCombo {{
                background: {input_bg}; color: {text}; border: 1px solid {border};
                border-radius: 9px; padding: 0 10px;
            }}
            QComboBox#modelCombo::drop-down {{ border: none; width: 28px; }}
            QComboBox QAbstractItemView {{
                background: {card}; color: {text}; selection-background-color: {accent};
                border: 1px solid {border}; outline: 0;
            }}
            QPushButton {{ font-family: "Microsoft YaHei UI"; }}
            QPushButton#primaryButton {{
                background: {accent}; color: white; border: none; border-radius: 10px;
                font-size: 14px; font-weight: 650;
            }}
            QPushButton#primaryButton:hover {{ background: {accent_hover}; }}
            QPushButton#primaryButton:disabled {{ background: #7E91C2; color: #DDE3F2; }}
            QPushButton#secondaryButton, QPushButton#iconButton {{
                background: transparent; color: {text}; border: 1px solid {border}; border-radius: 9px;
                padding: 7px 12px;
            }}
            QPushButton#secondaryButton:hover, QPushButton#iconButton:hover {{ background: {hover}; }}
            QPushButton#secondaryButton:disabled {{ color: {muted}; background: transparent; }}
            QPushButton#sidebarAction {{
                background: transparent;
                color: {text};
                border: none;
                border-radius: 9px;

                text-align: left;

                padding-top: 10px;
                padding-bottom: 10px;
                padding-left: 12px;
                padding-right: 10px;

                font-size: 12px;
            }}
            QPushButton#sidebarAction:hover {{ background: {hover}; }}
            QPushButton#linkButton {{
                background: transparent; color: {accent}; border: none; padding: 3px 0; text-align: left;
            }}
            QPushButton#linkButton:hover {{ color: {accent_hover}; }}
            QPushButton#windowButton, QPushButton#windowButtonClose {{
                background: transparent; border: none; border-radius: 7px; padding: 0;
            }}
            QPushButton#windowButton:hover {{ background: {hover}; }}
            QPushButton#windowButtonClose:hover {{ background: #C42B1C; }}

            QPushButton#activityToggleButton {{
                background: transparent;
                color: {muted};
                border: none;
                border-radius: 7px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#activityToggleButton:hover {{
                color: {accent};
                background: {hover};
            }}

            QFrame#aiActivityPanel {{
                background: {card};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QPushButton#activityPanelCloseButton {{
                background: transparent;
                color: {muted};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#activityPanelCloseButton:hover {{
                color: {accent};
                background: {hover};
            }}
            QLabel#activityPulse {{
                color: {muted};
                border: none;
                font-size: 11px;
                min-width: 18px;
                max-width: 18px;
                min-height: 18px;
                max-height: 18px;
            }}
            QLabel#activityPulse[bright="true"] {{
                color: {accent};
                font-size: 15px;
            }}
            QLabel#activityTitle {{
                color: {text};
                border: none;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#activityElapsed {{
                color: {muted};
                border: none;
                font-family: "Microsoft YaHei UI";
                font-size: 10px;
            }}
            QLabel#activityMetaKey {{
                color: {muted};
                border: none;
                font-size: 10px;
                font-weight: 600;
            }}
            QLabel#activityMetaValue {{
                color: {text};
                border: none;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#activitySectionTitle {{
                color: {muted};
                border: none;
                font-size: 10px;
                font-weight: 700;
                padding-top: 2px;
            }}
            QLabel#activityStageIcon {{
                color: {accent};
                border: none;
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#activityStageName {{
                color: {text};
                border: none;
                font-size: 11px;
                font-weight: 550;
            }}
            QLabel#activityStageTime {{
                color: {muted};
                border: none;
                font-family: "Microsoft YaHei UI";
                font-size: 10px;
            }}
            QLabel#activityHint {{
                color: {muted};
                border: none;
                font-size: 10px;
                padding-top: 1px;
            }}
            QTextBrowser#resultBrowser {{
                background: {result_bg}; color: {text}; border: none; border-radius: 10px;
                padding: 9px; font-family: "Microsoft YaHei UI"; font-size: 13px;
                selection-background-color: {accent};
            }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
            QScrollBar::handle:vertical {{ background: #7D8795; border-radius: 3px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """
        )
        if hasattr(self, "theme_toggle"):
            self.theme_toggle.setChecked(dark)

            self.theme_toggle.setToolTip(
                "切换到浅色模式"
                if dark
                else "切换到深色模式"
            )

            self.theme_toggle.update()

        if hasattr(self, "progress_bar"):
            self.progress_bar.update()
        if hasattr(self, "activity_wait_bar"):
            self.activity_wait_bar.update()

        self._update_ui_icons(text=text, muted=muted)
        self.result_browser.document().setDefaultStyleSheet(
            f"""
            body {{ color: {text}; font-family: 'Microsoft YaHei UI'; line-height: 1.55; }}
            h1 {{ font-size: 24px; margin: 14px 0 9px 0; }}
            h2 {{ font-size: 20px; margin: 13px 0 8px 0; }}
            h3 {{ font-size: 17px; margin: 12px 0 7px 0; }}
            p {{ margin: 6px 0; }}
            li {{ margin: 4px 0; }}
            blockquote {{ color: {muted}; border-left: 3px solid {accent}; margin-left: 8px; padding-left: 10px; }}
            code {{ font-family: "Microsoft YaHei UI"; background-color: {soft}; }}
            """
        )
        if self.result_markdown:
            self.result_browser.setMarkdown(self.result_markdown)

    def _update_ui_icons(self, text: str | None = None, muted: str | None = None) -> None:
        """Refresh vector icons for the active theme; no icon-font dependency."""
        if text is None or muted is None:
            if self.theme == "dark":
                text, muted = "#F2F4F8", "#929CAA"
            else:
                text, muted = "#141820", "#747E8C"

        if hasattr(self, "min_button"):
            self.min_button.setIcon(make_icon("minimize", text, text))
        if hasattr(self, "max_button"):
            kind = "restore" if self.isMaximized() else "maximize"
            self.max_button.setIcon(make_icon(kind, text, text))
        if hasattr(self, "close_button"):
            self.close_button.setIcon(make_icon("close", text, "#FFFFFF"))

        if hasattr(self, "refresh_models_button"):
            self.refresh_models_button.setIcon(make_icon("refresh", muted, text))
            self.refresh_models_button.setIconSize(QSize(17, 17))

    # ------------------------------------------------------------------
    # Settings / input
    # ------------------------------------------------------------------

    def _refresh_config_labels(self) -> None:
        self.api_status.setText("●  API Key 已配置" if self.api_key else "●  API Key 未配置")
        cookie = Path(self.settings.cookie_file).name if self.settings.cookie_file else "未使用"
        self.cookie_status.setText(f"Cookie：{cookie}")

    def set_api_key(self) -> None:
        value, ok = QInputDialog.getText(
            self,
            "Gemini API Key",
            "请输入 Gemini API Key：\n将保存在 ~/.bili_summarizer/api_key.txt",
            QLineEdit.EchoMode.Password,
        )
        if ok and value.strip():
            save_api_key(value.strip())
            self.api_key = value.strip()
            self._refresh_config_labels()
            self._set_status("API Key 已保存")
            self.refresh_models()

    def set_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Netscape 格式 Cookie 文件（可选）",
            "",
            "Cookie text (*.txt);;All files (*.*)",
        )
        if path:
            self.settings.cookie_file = path
            save_settings(self.settings)
            self._refresh_config_labels()
            return

        if self.settings.cookie_file:
            answer = QMessageBox.question(
                self,
                "Cookie",
                "没有选择新文件。是否清除当前 Cookie 设置？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.settings.cookie_file = ""
                save_settings(self.settings)
                self._refresh_config_labels()

    def _model_changed(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        self.settings.model = value
        save_settings(self.settings)

    def refresh_models(self) -> None:
        self.api_key = load_api_key()
        if not self.api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先配置 Gemini API Key。")
            return
        if self.model_thread and self.model_thread.isRunning():
            return

        self.refresh_models_button.setEnabled(False)
        self._set_status("正在刷新模型…")
        self.model_thread = ModelRefreshThread(self.api_key, self)
        self.model_thread.models_ready.connect(self._apply_models)
        self.model_thread.failed.connect(self._model_refresh_failed)
        self.model_thread.finished.connect(self._finish_model_refresh)
        self.model_thread.finished.connect(self.model_thread.deleteLater)
        self.model_thread.start()

    def _finish_model_refresh(self) -> None:
        self.refresh_models_button.setEnabled(True)
        self.model_thread = None

    def _apply_models(self, models: list[str]) -> None:
        current = self.settings.model
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if current in models:
            self.model_combo.setCurrentText(current)
        else:
            self.model_combo.setCurrentIndex(0)
            self.settings.model = self.model_combo.currentText()
            save_settings(self.settings)
        self.model_combo.blockSignals(False)
        self._set_status(f"模型刷新完成 · {len(models)} 个")

    def _model_refresh_failed(self, message: str) -> None:
        self._set_status("模型刷新失败")
        QMessageBox.warning(self, "刷新模型失败", message)

    def _keep_download_changed(self, checked: bool) -> None:
        self.settings.keep_download = bool(checked)
        save_settings(self.settings)
        self._set_status(
            f"已开启保留音频 · {DOWNLOAD_DIR}"
            if checked
            else "已关闭保留音频 · 总结后自动清理临时文件"
        )

    def open_download_dir(self) -> None:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(DOWNLOAD_DIR))):
            QMessageBox.warning(self, "无法打开目录", f"请手动打开：\n{DOWNLOAD_DIR}")

    def choose_file(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED_MEDIA)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择本地音视频文件",
            "",
            f"Media ({patterns});;All files (*.*)",
        )
        if path:
            self._set_local_file(path)

    def _set_local_file(self, path: str) -> None:
        path = str(Path(path))
        if Path(path).suffix.lower() not in SUPPORTED_MEDIA:
            QMessageBox.warning(self, "格式不支持", "请拖入常见音频或视频文件。")
            return
        self.local_file = path
        self.file_name_label.setText(Path(path).name)
        self.file_path_label.setText(path)
        self.url_edit.clear()
        self._set_status("已选择本地文件")

    def _url_edited(self, text: str) -> None:
        if text.strip() and self.local_file:
            self._clear_local_file()

    def _clear_local_file(self) -> None:
        self.local_file = ""
        self.file_name_label.setText("拖入本地音视频文件")
        self.file_path_label.setText("支持 m4s / mp3 / mp4 / m4a / wav 等常见格式")

    def clear_inputs(self) -> None:
        self.url_edit.clear()
        self._clear_local_file()
        self._set_status("输入已清空")

    def paste_url(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
            self._clear_local_file()

    def enter_result_mode(self) -> None:
        """
        总结完成后自动进入结果优先模式。
        输入区和进度区折叠成一条紧凑信息栏。
        """

        if self.focus_mode:
            self.exit_focus_mode()

        self.result_mode = True
        self.task_details_expanded = False

        if getattr(self, "activity_panel_expanded", False):
            self.activity_panel_expanded = False
            self.activity_panel.hide()
            self.activity_toggle_button.setText("查看任务状态  ▾")

        self.input_card.hide()
        self.progress_card.hide()

        self.task_compact_bar.show()

        self.task_toggle_button.setText(
            "▶  视频与任务信息"
        )

        self.task_summary_label.setText(
            "总结完成 · 100%"
        )

        self.focus_button.setEnabled(True)

        # 确保 Markdown 从顶部开始阅读
        self.result_browser.verticalScrollBar().setValue(0)

        self.result_browser.setFocus()

    def leave_result_mode(self) -> None:
        """
        回到普通工作状态。
        新任务开始时调用。
        """

        if self.focus_mode:
            self.exit_focus_mode()

        self.result_mode = False
        self.task_details_expanded = False

        self.task_compact_bar.hide()

        self.input_card.show()
        self.progress_card.show()

        self.task_toggle_button.setText(
            "▶  视频与任务信息"
        )

    def toggle_task_details(self) -> None:
        """
        在结果模式下展开/折叠原来的输入和任务区域。
        """

        if not self.result_mode:
            return

        self.task_details_expanded = (
            not self.task_details_expanded
        )

        if self.task_details_expanded:

            self.input_card.show()
            self.progress_card.show()

            self.task_toggle_button.setText(
                "▼  视频与任务信息"
            )

        else:

            if getattr(self, "activity_panel_expanded", False):
                self.activity_panel_expanded = False
                self.activity_panel.hide()
                self.activity_toggle_button.setText("查看任务状态  ▾")

            self.input_card.hide()
            self.progress_card.hide()

            self.task_toggle_button.setText(
                "▶  视频与任务信息"
            )

    def toggle_focus_mode(self) -> None:
        if self.focus_mode:
            self.exit_focus_mode()
        else:
            self.enter_focus_mode()

    def _escape_focus_mode(self) -> None:
        if self.focus_mode:
            self.exit_focus_mode()

    def enter_focus_mode(self) -> None:
        if not self.result_markdown:
            return

        self.focus_mode = True

        if getattr(self, "activity_panel_expanded", False):
            self.activity_panel_expanded = False
            self.activity_panel.hide()
            self.activity_toggle_button.setText("查看任务状态  ▾")

        # 左侧栏完全隐藏
        self.sidebar.hide()

        # 页面标题隐藏
        self.page_header.hide()

        # 输入 / 任务信息全部隐藏
        self.task_compact_bar.hide()
        self.input_card.hide()
        self.progress_card.hide()

        # 内容区尽量使用窗口空间
        self.main_layout.setContentsMargins(
            18,
            0,
            18,
            18,
        )

        self.main_layout.setSpacing(8)

        self.focus_button.setText(
            "退出专注"
        )

        self.focus_button.setToolTip(
            "返回正常工作界面"
        )

        self.result_browser.setFocus()

    def exit_focus_mode(self) -> None:
        if not self.focus_mode:
            return

        self.focus_mode = False

        self.sidebar.show()
        self.page_header.show()

        self.main_layout.setContentsMargins(
            28,
            0,
            24,
            24,
        )

        self.main_layout.setSpacing(16)

        self.focus_button.setText(
            "专注阅读"
        )

        self.focus_button.setToolTip(
            "让总结内容占据整个工作区域"
        )

        # 根据退出专注前所处模式恢复 UI
        if self.result_mode:

            self.task_compact_bar.show()

            if self.task_details_expanded:

                self.input_card.show()
                self.progress_card.show()

                self.task_toggle_button.setText(
                    "▼  视频与任务信息"
                )

            else:

                self.input_card.hide()
                self.progress_card.hide()

                self.task_toggle_button.setText(
                    "▶  视频与任务信息"
                )

        else:

            self.task_compact_bar.hide()
            self.input_card.show()
            self.progress_card.show()

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def start_processing(self) -> None:
        if self.processing_thread and self.processing_thread.isRunning():
            return

        self.api_key = load_api_key()
        if not self.api_key:
            QMessageBox.warning(self, "缺少 API Key", "请先在左侧配置 Gemini API Key。")
            return

        url = self.url_edit.text().strip()
        local = self.local_file.strip()
        if not url and not local:
            QMessageBox.warning(self, "缺少输入", "请输入 B 站链接，或选择本地音视频文件。")
            return
        # 新任务开始，退出阅读优先状态
        self.leave_result_mode()

        self.focus_button.setEnabled(False)

        self.result_markdown = ""
        self.result_browser.clear()
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.start_button.setText("处理中…")

        self._start_activity(url=url, local_file=local)
        self._apply_progress(0, "准备任务…")

        self.latest_log.parent.mkdir(parents=True, exist_ok=True)
        self.latest_log.write_text(
            f"=== {datetime.now().isoformat(timespec='seconds')} ===\n",
            encoding="utf-8",
        )

        # Snapshot the UI settings so changing widgets cannot mutate an active job.
        self.processing_thread = ProcessingThread(
            url=url,
            local_file=local,
            api_key=self.api_key,
            model=self.settings.model,
            cookie_file=self.settings.cookie_file,
            keep_download=bool(self.settings.keep_download),
            latest_log=self.latest_log,
            parent=self,
        )
        self.processing_thread.progress_changed.connect(self._apply_progress)
        self.processing_thread.media_info_ready.connect(self._apply_media_info)
        self.processing_thread.result_ready.connect(self._show_result)
        self.processing_thread.failed.connect(self._show_error)
        self.processing_thread.finished.connect(self._finish_processing)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    # ------------------------------------------------------------------
    # Rich live processing feedback
    # ------------------------------------------------------------------

    @staticmethod
    def _format_clock(seconds: float) -> str:
        seconds = max(0, int(seconds))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    @staticmethod
    def _format_stage_duration(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, sec = divmod(int(seconds), 60)
        if minutes < 60:
            return f"{minutes}:{sec:02d}"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{sec:02d}"

    @staticmethod
    def _format_bytes(size: int) -> str:
        size = max(0, int(size))
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{size} B"

    def _start_activity(self, *, url: str, local_file: str) -> None:
        now = time.monotonic()

        self.activity_running = True
        self.activity_stage = "source"
        self.activity_stage_started = now
        self.activity_task_started = now
        self.activity_inference_started = 0.0
        self.activity_stage_durations = {}
        self.activity_tick_count = 0
        self.activity_pulse_bright = False
        self.indeterminate_mode = False
        self.indeterminate_phase = 0.0
        self.indeterminate_animation.stop()
        self.activity_media_info = {}
        self.activity_failed_stage = None
        self.activity_model_desc = str(self.settings.model or "").strip() or "Gemini"

        if url:
            self.activity_source_kind = "bilibili"
            self.activity_source_desc = "B站视频链接"
        else:
            self.activity_source_kind = "local"
            file_path = Path(local_file)
            name = file_path.name or "本地媒体"
            if len(name) > 42:
                name = name[:19] + "…" + name[-19:]
            try:
                size = self._format_bytes(file_path.stat().st_size)
                self.activity_source_desc = f"{name} · {size}"
            except OSError:
                self.activity_source_desc = name

        self.activity_title.setText("任务处理中")
        self.activity_elapsed_label.setText("总耗时 00:00")
        self.activity_hint_label.setText("正在准备媒体，请稍候…")
        self.activity_panel_expanded = False
        self.activity_panel.hide()
        self.activity_toggle_button.setText("查看任务状态  ▾")
        self._refresh_activity_info()
        self._render_activity_timeline(now)

        self.activity_pulse.setProperty("bright", False)
        self.activity_pulse.style().unpolish(self.activity_pulse)
        self.activity_pulse.style().polish(self.activity_pulse)

        self.activity_timer.start()

    def _stage_from_progress(self, percent: int, text: str) -> str:
        if percent >= 100 or "总结完成" in text:
            return "complete"
        if percent >= 72 or ("正在总结视频" in text and "完成" not in text):
            return "inference"
        if percent >= 55 or "Gemini" in text:
            return "upload"
        if percent >= 38:
            return "normalize"
        return "source"

    def _transition_activity(self, new_stage: str) -> None:
        if not self.activity_running:
            return

        now = time.monotonic()
        old_stage = self.activity_stage

        if new_stage == old_stage:
            return

        if old_stage in {"source", "normalize", "upload", "inference"}:
            elapsed = max(0.0, now - self.activity_stage_started)
            self.activity_stage_durations[old_stage] = (
                    self.activity_stage_durations.get(old_stage, 0.0) + elapsed
            )

        self.activity_stage = new_stage
        self.activity_stage_started = now

        if new_stage == "upload":
            self.activity_title.setText("Gemini 正在准备音频")
            self.activity_hint_label.setText(
                "音频正在上传或由 Gemini Files API 处理，完成后会自动进入模型分析。"
            )

        elif new_stage == "inference":
            self.activity_inference_started = now
            self.indeterminate_mode = True
            self.indeterminate_phase = 0.0
            self.progress_bar.set_indeterminate(True)
            self.progress_bar.set_phase(0.0)
            self.activity_wait_bar.set_indeterminate(True)
            self.activity_wait_bar.set_phase(0.0)

            self.indeterminate_animation.stop()
            self.indeterminate_animation.start()
            self.activity_title.setText("Gemini 正在生成视频笔记")
            self.activity_hint_label.setText(
                "已向模型提交完整音频，正在等待 Gemini 返回总结。程序仍在正常运行。"
            )

        elif new_stage == "complete":
            self._complete_activity(success=True)
            return

        self._render_activity_timeline(now)

    def _complete_activity(self, *, success: bool) -> None:
        now = time.monotonic()

        if self.activity_running and self.activity_stage in {
            "source",
            "normalize",
            "upload",
            "inference",
        }:
            elapsed = max(0.0, now - self.activity_stage_started)
            self.activity_stage_durations[self.activity_stage] = (
                    self.activity_stage_durations.get(self.activity_stage, 0.0) + elapsed
            )

        self.activity_running = False
        self.indeterminate_mode = False
        self.indeterminate_animation.stop()
        self.activity_timer.stop()

        total = (
            max(0.0, now - self.activity_task_started)
            if self.activity_task_started
            else 0.0
        )

        if success:
            self.activity_failed_stage = None
            self.activity_stage = "complete"
            self.activity_title.setText("处理完成")
            self.activity_hint_label.setText(
                f"全部阶段已完成 · 总耗时 {self._format_clock(total)}"
            )
            self.activity_pulse.setProperty("bright", True)
            self.activity_wait_bar.set_indeterminate(False)
            self.activity_wait_bar.set_progress(100, animate=False)
        else:
            self.activity_failed_stage = self.activity_stage
            self.activity_stage = "failed"
            self.activity_title.setText("任务已中断")
            self.activity_hint_label.setText(
                "任务没有正常完成。请查看上方错误信息或下载日志。"
            )
            self.activity_pulse.setProperty("bright", False)
            self.activity_wait_bar.set_indeterminate(False)
            self.activity_wait_bar.set_progress(
                self.current_progress,
                animate=False,
            )

        self.activity_pulse.style().unpolish(self.activity_pulse)
        self.activity_pulse.style().polish(self.activity_pulse)
        self.activity_elapsed_label.setText(
            f"总耗时 {self._format_clock(total)}"
        )
        self._render_activity_timeline(now)

    def _apply_media_info(self, info: dict) -> None:
        self.activity_media_info = dict(info or {})
        self._refresh_activity_info()

    def _refresh_activity_info(self) -> None:
        model = self.activity_model_desc or str(self.settings.model or "").strip() or "Gemini"
        source = self.activity_source_desc or "等待输入"

        prepared_bytes = int(self.activity_media_info.get("prepared_bytes", 0) or 0)
        source_bytes = int(self.activity_media_info.get("source_bytes", 0) or 0)

        if prepared_bytes:
            audio_text = self._format_bytes(prepared_bytes)
        elif source_bytes:
            audio_text = f"待转换 · 输入 {self._format_bytes(source_bytes)}"
        else:
            audio_text = "等待音频准备"

        self.activity_model_value.setText(model)
        self.activity_source_value.setText(source)
        self.activity_audio_value.setText(audio_text)

    def _current_stage_elapsed(self, stage: str, now: float) -> float:
        value = float(self.activity_stage_durations.get(stage, 0.0))
        if self.activity_running and self.activity_stage == stage:
            value += max(0.0, now - self.activity_stage_started)
        return value

    def _render_activity_timeline(self, now: float | None = None) -> None:
        if not hasattr(self, "activity_stage_icon_labels"):
            return

        now = time.monotonic() if now is None else now

        source_name = (
            "获取 B站音频"
            if self.activity_source_kind == "bilibili"
            else "读取本地媒体"
        )
        self.activity_stage_name_labels["source"].setText(source_name)

        stages = [
            ("source", source_name),
            ("normalize", "音频预处理"),
            ("upload", "上传 / 处理 Gemini 音频"),
            ("inference", "AI 生成结构化摘要"),
        ]

        order = ["source", "normalize", "upload", "inference"]
        current_index = (
            order.index(self.activity_stage)
            if self.activity_stage in order
            else len(order)
        )

        for index, (key, _label) in enumerate(stages):
            duration = self._current_stage_elapsed(key, now)

            if key == self.activity_failed_stage:
                icon = "×"
                timing = self._format_stage_duration(duration)
            elif key in self.activity_stage_durations:
                icon = "✓"
                timing = self._format_stage_duration(duration)
            elif self.activity_running and self.activity_stage == key:
                icon = "●"
                timing = self._format_clock(duration)
            elif self.activity_stage == "complete":
                icon = "✓"
                timing = self._format_stage_duration(duration)
            elif index < current_index:
                icon = "✓"
                timing = self._format_stage_duration(duration)
            else:
                icon = "○"
                timing = "等待"

            self.activity_stage_icon_labels[key].setText(icon)
            self.activity_stage_time_labels[key].setText(timing)

    def _position_activity_panel(self) -> None:
        """Place the floating task-status card under the dropdown trigger.

        The panel deliberately overlays the page instead of participating in
        the main QVBoxLayout; therefore opening it can never squeeze the stage
        rows or the result area.
        """
        if not hasattr(self, "activity_panel"):
            return

        margin = 24
        gap = 8
        available_width = max(360, self.main_panel.width() - margin * 2)
        width = min(760, available_width)
        height = min(410, max(350, self.main_panel.height() - 110))

        anchor = self.activity_toggle_button.mapTo(
            self.main_panel,
            self.activity_toggle_button.rect().bottomRight(),
        )

        x = anchor.x() - width
        x = max(margin, min(x, self.main_panel.width() - margin - width))

        y = anchor.y() + gap
        bottom_limit = self.main_panel.height() - margin
        if y + height > bottom_limit:
            y = max(48, bottom_limit - height)

        self.activity_panel.setGeometry(x, y, width, height)

    def toggle_activity_panel(self) -> None:
        """Show/hide detailed task telemetry without affecting the running job."""
        self.activity_panel_expanded = not self.activity_panel_expanded

        if self.activity_panel_expanded:
            self._refresh_activity_info()
            self._render_activity_timeline()
            self._position_activity_panel()
            self.activity_panel.show()
            self.activity_panel.raise_()
            self.activity_toggle_button.setText("收起任务状态  ▴")
            self._sync_activity_wait_fill(animate=False)
        else:
            self.activity_panel.hide()
            self.activity_toggle_button.setText("查看任务状态  ▾")

    def _activity_hint_for_wait(self, seconds: float) -> str:
        if seconds < 10:
            return "Gemini 已接收生成请求，正在准备响应…"
        if seconds < 30:
            return "正在等待 Gemini 返回完整总结。程序仍在正常运行，请稍候…"
        if seconds < 60:
            return "长视频分析通常需要更多时间；当前请求仍在处理中。"
        if seconds < 120:
            return (
                "已等待较长时间。模型负载和网络状况可能影响响应速度，"
                "请保持程序开启。"
            )
        return (
            "Gemini 请求仍在等待响应。若服务最终返回超时或错误，"
            "程序会明确提示；当前无需重复点击。"
        )

    def _tick_activity(self) -> None:
        if not self.activity_running:
            return

        now = time.monotonic()
        self.activity_tick_count += 1

        total = max(0.0, now - self.activity_task_started)
        self.activity_elapsed_label.setText(
            f"总耗时 {self._format_clock(total)}"
        )

        # Gentle breathing dot: two states, updated only twice per second.
        if self.activity_tick_count % 2 == 0:
            self.activity_pulse_bright = not self.activity_pulse_bright
            self.activity_pulse.setProperty(
                "bright",
                self.activity_pulse_bright,
            )
            self.activity_pulse.style().unpolish(self.activity_pulse)
            self.activity_pulse.style().polish(self.activity_pulse)

        if self.activity_stage == "inference":
            wait = max(0.0, now - self.activity_inference_started)
            self.activity_hint_label.setText(
                f"AI 已等待 {self._format_clock(wait)} · "
                f"{self._activity_hint_for_wait(wait)}"
            )

            # The indeterminate bars are animated continuously by
            # QVariantAnimation; this timer only updates text/elapsed time.

        elif self.activity_stage == "upload":
            self.activity_hint_label.setText(
                "Gemini 正在接收或处理上传音频；这一阶段完成后会自动进入 AI 分析。"
            )
            self._sync_activity_wait_fill()

        self._render_activity_timeline(now)

    def _on_indeterminate_phase(self, value) -> None:
        if not self.indeterminate_mode:
            return
        self.indeterminate_phase = float(value)
        self._sync_progress_fill(animate=False)
        self._sync_activity_wait_fill(animate=False)

    @staticmethod
    def _indeterminate_ratio(phase: float) -> float:
        # 0 -> 1 -> 0 with smooth zero-velocity turns at both edges.
        import math
        return 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)

    @staticmethod
    def _animate_geometry(
            animation: QPropertyAnimation,
            widget: QWidget,
            target: QRect,
            *,
            animate: bool,
    ) -> None:
        if not animate:
            animation.stop()
            widget.setGeometry(target)
            return

        current = widget.geometry()
        if current == target:
            return

        animation.stop()
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.start()

    def _sync_activity_wait_fill(self, *, animate: bool = True) -> None:
        if not hasattr(self, "activity_wait_bar"):
            return

        self.activity_wait_bar.set_indeterminate(self.indeterminate_mode)
        if self.indeterminate_mode:
            self.activity_wait_bar.set_phase(self.indeterminate_phase)
        else:
            self.activity_wait_bar.set_progress(
                self.current_progress,
                animate=animate,
            )

    def _apply_progress(self, percent: int, text: str) -> None:
        percent = max(0, min(100, int(percent)))

        stage = self._stage_from_progress(percent, text)
        self._transition_activity(stage)

        self.current_progress = percent

        if self.indeterminate_mode and stage == "inference":
            self.percent_label.setText("AI 处理中")
        else:
            self.percent_label.setText(f"{percent}%")

        self._sync_progress_fill()
        self._sync_activity_wait_fill()

        self.progress_text.setText(text)
        self._set_status(text)

    def _sync_progress_fill(self, *, animate: bool = True) -> None:
        if not hasattr(self, "progress_bar"):
            return

        self.progress_bar.set_indeterminate(self.indeterminate_mode)
        if self.indeterminate_mode:
            self.progress_bar.set_phase(self.indeterminate_phase)
        else:
            self.progress_bar.set_progress(
                self.current_progress,
                animate=animate,
            )

    def _show_result(self, result: str) -> None:
        self.result_markdown = result

        self.result_browser.setMarkdown(
            result
        )

        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.focus_button.setEnabled(True)

        self._apply_progress(
            100,
            "总结完成",
        )

        # ===================================
        # 自动进入结果优先模式
        # ===================================

        self.enter_result_mode()

    def _show_error(self, message: str) -> None:
        self._complete_activity(success=False)
        self._set_status("处理失败", error=True)
        self.progress_text.setText("处理失败")
        self.result_browser.setPlainText(
            f"❌ {message}\n\n下载相关详细信息：\n{self.latest_log}"
        )
        QMessageBox.critical(self, "处理失败", message)

    def _finish_processing(self) -> None:
        self.start_button.setEnabled(True)
        self.start_button.setText("开始总结")
        self.processing_thread = None

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_pill.set_status(text, error=error)

    # ------------------------------------------------------------------
    # Result / log
    # ------------------------------------------------------------------

    def copy_result(self) -> None:
        if not self.result_markdown:
            return
        QApplication.clipboard().setText(self.result_markdown)
        self._set_status("Markdown 已复制")

    def save_result(self) -> None:
        if not self.result_markdown:
            QMessageBox.information(self, "提示", "当前还没有总结结果。")
            return
        default_name = f"bili_summary_{datetime.now():%Y%m%d_%H%M%S}.md"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 Markdown",
            default_name,
            "Markdown (*.md);;Text (*.txt)",
        )
        if path:
            Path(path).write_text(self.result_markdown, encoding="utf-8")
            self._set_status("Markdown 已保存")

    def show_log(self) -> None:
        try:
            text = self.latest_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = "暂时没有下载日志。"
        self.log_window = LogWindow(text, self)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.processing_thread and self.processing_thread.isRunning():
            QMessageBox.information(
                self,
                "任务进行中",
                "当前正在下载、处理或总结音频。为避免中断临时文件和云端清理，请等待任务完成后再关闭。",
            )
            event.ignore()
            return
        if self.model_thread and self.model_thread.isRunning():
            QMessageBox.information(
                self,
                "正在刷新模型",
                "模型列表正在刷新，请等待几秒后再关闭。",
            )
            event.ignore()
            return
        event.accept()


def run() -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setStyle("Fusion")

    # Global font baseline: labels, buttons, inputs, combo boxes,
    # dialogs and other Qt controls inherit Microsoft YaHei UI.
    app_font = QFont(APP_FONT_FAMILY, APP_FONT_SIZE)
    app.setFont(app_font)

    window = MainWindow()
    window.show()
    app.exec()
