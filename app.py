from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, QSize, QThread, Qt, QUrl, Signal
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
    """
    顶部浅色 / 深色主题切换按钮。

    checked = True  -> Dark
    checked = False -> Light
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setCheckable(True)
        self.setFixedSize(56, 32)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.setToolTip("切换深色 / 浅色模式")

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        dark = self.isChecked()

        # =========================
        # 颜色
        # =========================

        if dark:
            track_color = QColor("#252A35")
            border_color = QColor("#353C49")
            knob_color = QColor("#343B49")

            moon_color = QColor("#FFD166")

        else:
            track_color = QColor("#EEF2FA")
            border_color = QColor("#DDE3EE")
            knob_color = QColor("#FFFFFF")

            sun_color = QColor("#F4A62A")

        # =========================
        # 开关轨道
        # =========================

        track_rect = QRectF(
            0.5,
            0.5,
            self.width() - 1,
            self.height() - 1,
        )

        painter.setPen(
            QPen(border_color, 1)
        )

        painter.setBrush(track_color)

        painter.drawRoundedRect(
            track_rect,
            16,
            16,
        )

        # =========================
        # 滑块位置
        # =========================

        knob_size = 26

        if dark:
            knob_x = self.width() - knob_size - 3
        else:
            knob_x = 3

        knob_y = 3

        knob_rect = QRectF(
            knob_x,
            knob_y,
            knob_size,
            knob_size,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)

        painter.drawEllipse(knob_rect)

        cx = knob_rect.center().x()
        cy = knob_rect.center().y()

        # =========================
        # Light → 太阳
        # =========================

        if not dark:

            painter.setPen(
                QPen(
                    sun_color,
                    1.7,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )

            painter.setBrush(Qt.BrushStyle.NoBrush)

            # 中心太阳
            painter.drawEllipse(
                QRectF(
                    cx - 4,
                    cy - 4,
                    8,
                    8,
                )
            )

            # 八条阳光
            rays = [
                ((0, -8), (0, -6)),
                ((0, 8), (0, 6)),
                ((-8, 0), (-6, 0)),
                ((8, 0), (6, 0)),

                ((-5.7, -5.7), (-4.3, -4.3)),
                ((5.7, 5.7), (4.3, 4.3)),
                ((5.7, -5.7), (4.3, -4.3)),
                ((-5.7, 5.7), (-4.3, 4.3)),
            ]

            for start, end in rays:
                painter.drawLine(
                    QPointF(
                        cx + start[0],
                        cy + start[1],
                    ),
                    QPointF(
                        cx + end[0],
                        cy + end[1],
                    ),
                )

        # =========================
        # Dark → 月亮
        # =========================

        else:

            moon = QPainterPath()

            moon.addEllipse(
                QRectF(
                    cx - 6,
                    cy - 6,
                    12,
                    12,
                )
            )

            cut = QPainterPath()

            cut.addEllipse(
                QRectF(
                    cx - 2,
                    cy - 7,
                    11,
                    11,
                )
            )

            moon = moon.subtracted(cut)

            painter.fillPath(
                moon,
                moon_color,
            )

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
        box.setFont(QFont("Consolas", 10))
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
        if hasattr(self, "progress_track"):
            self._sync_progress_fill()

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
        title = QLabel("Bili Summary", brand)
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
            "Segoe UI Emoji",
            "Microsoft YaHei UI",
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
        self.progress_track = QFrame(progress_card)
        self.progress_track.setObjectName("progressTrack")
        self.progress_track.setFixedHeight(7)
        self.progress_fill = QFrame(self.progress_track)
        self.progress_fill.setObjectName("progressFill")
        self.progress_fill.setGeometry(0, 0, 0, 7)
        bar_row.addWidget(self.progress_track, 1)
        self.percent_label = QLabel("0%", progress_card)
        self.percent_label.setObjectName("monoMuted")
        self.percent_label.setFixedWidth(42)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.percent_label)
        progress_layout.addLayout(bar_row)

        self.progress_text = QLabel("就绪", progress_card)
        self.progress_text.setObjectName("mutedText")
        progress_layout.addWidget(self.progress_text)
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

        self._apply_theme()

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
            QLabel#monoMuted {{ color: {muted}; font-family: Consolas; font-size: 10px; }}
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
            QFrame#progressTrack {{ background: {soft}; border: none; border-radius: 3px; }}
            QFrame#progressFill {{ background: {accent}; border: none; border-radius: 3px; }}
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
            code {{ font-family: Consolas; background-color: {soft}; }}
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
        self.processing_thread.result_ready.connect(self._show_result)
        self.processing_thread.failed.connect(self._show_error)
        self.processing_thread.finished.connect(self._finish_processing)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.start()

    def _apply_progress(self, percent: int, text: str) -> None:
        percent = max(0, min(100, int(percent)))
        self.current_progress = percent
        self._sync_progress_fill()
        self.percent_label.setText(f"{percent}%")
        self.progress_text.setText(text)
        self._set_status(text)

    def _sync_progress_fill(self) -> None:
        if not hasattr(self, "progress_track"):
            return
        width = max(0, self.progress_track.width())
        self.progress_fill.setGeometry(0, 0, int(width * self.current_progress / 100), 7)

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

    window = MainWindow()
    window.show()
    app.exec()
