from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QEvent, QEasingCurve, QPropertyAnimation, QSettings, QSize, QTimer, Qt, QUrl,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QSizePolicy, QTextBrowser, QVBoxLayout, QWidget, QDialog,
)

from settings import DOWNLOAD_DIR, LOG_DIR, load_api_key, load_api_keys, load_model_cache, load_settings, save_api_key, save_model_cache, save_settings
from workers import ModelRefreshThread, ProcessingThread
from ui_widgets import (
    APP_EMOJI_FAMILY, APP_FONT_FAMILY, APP_FONT_SIZE, SUPPORTED_MEDIA, DragArea,
    DropCard, LogWindow, ResizeHandle, SmartComboBox, SmoothProgressBar, StatusPill, ThemeFadeOverlay,
    ThemeToggle, ToggleSwitch, make_icon,
)
from dialogs import FriendlyErrorDialog, SettingsDialog, ToastManager, classify_error
from ai.base import ProviderError
from ai.catalog import PROVIDERS, provider_display_name, provider_fallback_models
from ai.manager import validate_provider_configuration

APP_ORG = "codeNiuMa"
APP_NAME = "Bilibili Video Summarizer"

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
        self.api_keys = load_api_keys()

        # Restore the last successfully refreshed provider model lists from
        # disk. This makes model selectors useful immediately after startup;
        # users only refresh when they actually want newer server data.
        cached_models = load_model_cache()
        self.models_by_provider = {}
        for provider_id in PROVIDERS:
            current_model = self.settings.get_model(provider_id)
            merged = list(dict.fromkeys(
                list(cached_models.get(provider_id, []))
                + ([current_model] if current_model else [])
                + provider_fallback_models(provider_id)
            ))
            self.models_by_provider[provider_id] = merged
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
        # Live processing feedback / AI provider activity
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

        # Smooth infinite movement used while AI inference has no real
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
        self.toasts = ToastManager(self.main_panel)
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
        if hasattr(self, "toasts"):
            self.toasts.reposition()

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

        layout.addWidget(self._section_label("AI 服务商"))
        self.provider_combo = SmartComboBox(self.sidebar, max_visible_items=8, max_popup_width=330)
        self.provider_combo.setObjectName("providerCombo")
        self.provider_combo.setMinimumHeight(42)
        for provider_id, spec in PROVIDERS.items():
            self.provider_combo.addItem(spec.display_name, provider_id)
        provider_index = self.provider_combo.findData(self.settings.provider)
        self.provider_combo.setCurrentIndex(provider_index if provider_index >= 0 else 0)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        layout.addWidget(self.provider_combo)

        layout.addWidget(self._section_label("AI 模型"))
        model_row = QHBoxLayout()
        model_row.setSpacing(7)
        self.model_combo = SmartComboBox(self.sidebar, max_visible_items=9, max_popup_width=460)
        self.model_combo.setObjectName("modelCombo")
        self.model_combo.setMinimumHeight(42)
        # 模型仅允许从列表选择，禁止手动输入任意模型名。
        self.model_combo.setEditable(False)
        current_provider = self.settings.provider
        model_values = list(self.models_by_provider.get(current_provider, []))
        current_model = self.settings.get_model(current_provider)
        if current_model and current_model not in model_values:
            model_values.insert(0, current_model)
        self.model_combo.addItems(model_values)
        self.model_combo.setCurrentText(current_model)
        self.model_combo.currentTextChanged.connect(self._model_changed)
        model_row.addWidget(self.model_combo, 1)

        self.refresh_models_button = QPushButton("", self.sidebar)
        self.refresh_models_button.setObjectName("iconButton")
        self.refresh_models_button.setFixedSize(42, 42)
        self.refresh_models_button.setToolTip("根据当前服务商 API Key 刷新可用模型")
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

        self.settings_button = QPushButton("⚙   设置", self.sidebar)
        self.settings_button.setObjectName("sidebarAction")
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)

        self.log_button = QPushButton("📜   下载日志", self.sidebar)
        self.log_button.setObjectName("sidebarAction")
        self.log_button.clicked.connect(self.show_log)
        layout.addWidget(self.log_button)

        emoji_font = QFont()
        emoji_font.setFamilies([APP_FONT_FAMILY, APP_EMOJI_FAMILY])
        emoji_font.setPointSize(11)
        self.settings_button.setFont(emoji_font)
        self.log_button.setFont(emoji_font)

        layout.addStretch(1)
        version = QLabel("PySide6 UI · 稳定流程", self.sidebar)
        version.setObjectName("mutedText")
        layout.addWidget(version)
        pipeline = QLabel("yt-dlp  →  FFmpeg  →  AI", self.sidebar)
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
        page_subtitle = QLabel("粘贴 B 站链接，或拖入本地音视频，让 AI 提炼核心内容。", header)
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
        self.activity_toggle_button.setToolTip("展开下载、音频处理、转写与 AI 推理的详细状态")
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

        audio_key = QLabel("AI 输入音频", self.activity_panel)
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

        self.activity_route_label = QLabel("", self.activity_panel)
        self.activity_route_label.setObjectName("activityRoute")
        self.activity_route_label.setWordWrap(True)
        self.activity_route_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        activity_layout.addWidget(self.activity_route_label)

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
            ("upload", "准备 AI 输入"),
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
            QComboBox#modelCombo, QComboBox#providerCombo {{
                background: {input_bg}; color: {text}; border: 1px solid {border};
                border-radius: 9px; padding: 0 34px 0 10px;
            }}
            QComboBox#modelCombo::drop-down, QComboBox#providerCombo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                border: none;
                width: 32px;
            }}
            QComboBox#modelCombo::down-arrow, QComboBox#providerCombo::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background: {card}; color: {text}; selection-background-color: {accent};
                selection-color: white; border: 1px solid {border}; outline: 0;
                padding: 3px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 30px;
                padding: 4px 8px;
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
        provider_id = self.settings.provider
        provider_name = provider_display_name(provider_id)
        key = load_api_key(provider_id)
        self.api_keys = load_api_keys()
        self.api_status.setText(
            f"●  {provider_name} 已配置" if key else f"●  {provider_name} 未配置"
        )
        cookie = Path(self.settings.cookie_file).name if self.settings.cookie_file else "未使用"
        self.cookie_status.setText(f"Cookie：{cookie}")

    def _toast(self, text: str, kind: str = "info", duration: int = 2600) -> None:
        self.toasts.show(text, kind=kind, duration=duration)

    def _sync_provider_controls(self) -> None:
        provider_id = self.settings.provider

        self.provider_combo.blockSignals(True)
        index = self.provider_combo.findData(provider_id)
        self.provider_combo.setCurrentIndex(index if index >= 0 else 0)
        self.provider_combo.blockSignals(False)

        current_model = self.settings.get_model(provider_id)
        models = list(self.models_by_provider.get(provider_id, []))
        if current_model and current_model not in models:
            models.insert(0, current_model)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(models)
        self.model_combo.setCurrentText(current_model)
        self.model_combo.blockSignals(False)

        self.refresh_models_button.setToolTip(
            f"刷新 {provider_display_name(provider_id)} 可用模型"
        )
        self._refresh_config_labels()

    def open_settings(self) -> None:
        self.api_keys = load_api_keys()
        # Keep the current sidebar model list in the provider cache before opening.
        active_provider = self.settings.provider
        self.models_by_provider[active_provider] = [
            self.model_combo.itemText(i)
            for i in range(self.model_combo.count())
            if self.model_combo.itemText(i).strip()
        ]

        dialog = SettingsDialog(
            provider_id=self.settings.provider,
            api_keys=self.api_keys,
            provider_models=dict(self.settings.provider_models),
            models_by_provider=dict(self.models_by_provider),
            transcription_provider=self.settings.transcription_provider,
            transcription_models=dict(self.settings.transcription_models),
            cookie_file=self.settings.cookie_file,
            keep_download=self.settings.keep_download,
            theme=self.theme,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        values = dialog.values()

        # Settings can refresh provider lists itself. Re-read the persistent
        # cache so those fresh lists immediately propagate back to the sidebar.
        refreshed_cache = load_model_cache()
        for provider_id, models in refreshed_cache.items():
            if models:
                self.models_by_provider[provider_id] = list(models)

        api_keys = dict(values["api_keys"])
        api_from_env = dict(values["api_from_env"])
        provider_models = dict(values["provider_models"])
        transcription_models = dict(values["transcription_models"])

        for provider_id in PROVIDERS:
            if not bool(api_from_env.get(provider_id, False)):
                save_api_key(
                    str(api_keys.get(provider_id) or "").strip(),
                    provider_id=provider_id,
                )

        self.api_keys = load_api_keys()
        self.settings.provider = str(values["provider"] or "gemini")
        for provider_id, model in provider_models.items():
            self.settings.set_model(provider_id, str(model or ""))
        self.settings.transcription_provider = str(
            values["transcription_provider"] or "auto"
        )
        for provider_id, model in transcription_models.items():
            self.settings.set_transcription_model(provider_id, str(model or ""))
        self.settings.cookie_file = str(values["cookie_file"] or "").strip()
        self.settings.keep_download = bool(values["keep_download"])
        save_settings(self.settings)

        for provider_id in PROVIDERS:
            cached = list(self.models_by_provider.get(provider_id, []))
            model = self.settings.get_model(provider_id)
            if model and model not in cached:
                cached.insert(0, model)
            self.models_by_provider[provider_id] = cached or provider_fallback_models(provider_id)

        self.keep_switch.blockSignals(True)
        self.keep_switch.setChecked(self.settings.keep_download)
        self.keep_switch.blockSignals(False)

        self._sync_provider_controls()
        self._toast("设置已保存", "success")

    def _provider_changed(self, index: int) -> None:
        provider_id = str(self.provider_combo.itemData(index) or "").strip()
        if not provider_id or provider_id not in PROVIDERS:
            return
        if provider_id == self.settings.provider:
            return

        # Persist the outgoing provider's current model before switching.
        old_provider = self.settings.provider
        old_model = self.model_combo.currentText().strip()
        if old_model:
            self.settings.set_model(old_provider, old_model)
            current_items = [
                self.model_combo.itemText(i)
                for i in range(self.model_combo.count())
                if self.model_combo.itemText(i).strip()
            ]
            self.models_by_provider[old_provider] = current_items

        self.settings.provider = provider_id
        save_settings(self.settings)
        self._sync_provider_controls()
        self._set_status(f"已切换到 {provider_display_name(provider_id)}")

    def _model_changed(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        provider_id = self.settings.provider
        self.settings.set_model(provider_id, value)
        if value not in self.models_by_provider.get(provider_id, []):
            self.models_by_provider.setdefault(provider_id, []).insert(0, value)
        save_settings(self.settings)

    def refresh_models(self) -> None:
        provider_id = self.settings.provider
        api_key = load_api_key(provider_id)
        if not api_key:
            self._toast(
                f"请先在设置中配置 {provider_display_name(provider_id)} API Key。",
                "warning",
            )
            self.open_settings()
            return
        if self.model_thread and self.model_thread.isRunning():
            return

        self.refresh_models_button.setEnabled(False)
        self.provider_combo.setEnabled(False)
        self._set_status(f"正在刷新 {provider_display_name(provider_id)} 模型…")
        self.model_thread = ModelRefreshThread(provider_id, api_key, self)
        self.model_thread.models_ready.connect(self._apply_models)
        self.model_thread.failed.connect(self._model_refresh_failed)
        self.model_thread.finished.connect(self._finish_model_refresh)
        self.model_thread.finished.connect(self.model_thread.deleteLater)
        self.model_thread.start()

    def _finish_model_refresh(self) -> None:
        self.refresh_models_button.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.model_thread = None

    def _apply_models(self, provider_id: str, models: list[str]) -> None:
        models = list(dict.fromkeys(
            str(model).strip()
            for model in models
            if str(model).strip()
        ))
        self.models_by_provider[provider_id] = models

        # Cache only successful non-empty refreshes. The next application start
        # will restore these lists without requiring another API request.
        save_model_cache(provider_id, models)

        current = self.settings.get_model(provider_id)

        if provider_id == self.settings.provider:
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
            elif models:
                self.model_combo.setCurrentIndex(0)
                self.settings.set_model(provider_id, self.model_combo.currentText())
                save_settings(self.settings)
            self.model_combo.blockSignals(False)

        self._set_status(f"模型刷新完成 · {len(models)} 个")
        self._toast(
            f"{provider_display_name(provider_id)} 已刷新 {len(models)} 个可用模型",
            "success",
        )

    def _model_refresh_failed(self, provider_id: str, message: str) -> None:
        self._set_status("模型刷新失败")
        self._toast(
            f"{provider_display_name(provider_id)} 模型列表刷新失败：{message}",
            "warning",
            4200,
        )

    def _keep_download_changed(self, checked: bool) -> None:
        self.settings.keep_download = bool(checked)
        save_settings(self.settings)
        self._set_status(
            f"已开启保留音频 · {DOWNLOAD_DIR}"
            if checked
            else "已关闭保留音频 · 总结后自动清理临时文件"
        )
        self._toast("已开启保留下载音频" if checked else "已关闭保留下载音频", "info")

    def open_download_dir(self) -> None:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(DOWNLOAD_DIR))):
            self._toast(f"无法自动打开目录，请手动打开：{DOWNLOAD_DIR}", "warning", 4200)

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
            self._toast("文件格式暂不支持，请选择常见音频或视频文件。", "warning")
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

        provider_id = self.settings.provider
        provider_name = provider_display_name(provider_id)
        self.api_keys = load_api_keys()

        if not self.api_keys.get(provider_id, "").strip():
            self._toast(f"开始任务前需要先配置 {provider_name} API Key。", "warning")
            self.open_settings()
            return

        try:
            validate_provider_configuration(
                provider_id,
                self.api_keys,
                self.settings.transcription_provider,
            )
        except ProviderError as exc:
            self._toast(str(exc), "warning", 4600)
            self.open_settings()
            return

        url = self.url_edit.text().strip()
        local = self.local_file.strip()
        if not url and not local:
            self._toast("请粘贴 B 站链接，或选择本地音视频文件。", "warning")
            return

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
            f"=== {datetime.now().isoformat(timespec='seconds')} ===\n"
            f"provider={provider_id} model={self.settings.get_model(provider_id)}\n"
            f"transcription={self._transcription_route_name()}\n",
            encoding="utf-8",
        )

        self.processing_thread = ProcessingThread(
            url=url,
            local_file=local,
            provider_id=provider_id,
            api_keys=dict(self.api_keys),
            provider_models=dict(self.settings.provider_models),
            transcription_provider=self.settings.transcription_provider,
            transcription_models=dict(self.settings.transcription_models),
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

    def _active_provider_name(self) -> str:
        return provider_display_name(self.settings.provider)

    def _transcription_provider_id(self) -> str:
        provider_id = self.settings.provider
        spec = PROVIDERS[provider_id]

        if spec.supports_direct_audio or spec.supports_transcription:
            return provider_id

        requested = self.settings.transcription_provider
        if requested in {"gemini", "openai"}:
            return requested

        # Mirror ai.manager auto resolution: Gemini first, then OpenAI.
        keys = self.api_keys or load_api_keys()
        if keys.get("gemini", "").strip():
            return "gemini"
        if keys.get("openai", "").strip():
            return "openai"
        return ""

    def _transcription_provider_name(self) -> str:
        provider_id = self._transcription_provider_id()
        return provider_display_name(provider_id) if provider_id else "音频转写服务"

    def _transcription_model_name(self) -> str:
        provider_id = self._transcription_provider_id()
        if not provider_id:
            return "未选择转写模型"
        return self.settings.get_transcription_model(provider_id)

    def _transcription_route_name(self) -> str:
        provider_id = self._transcription_provider_id()
        if not provider_id:
            return "音频转写服务未配置"
        return (
            f"{provider_display_name(provider_id)} · "
            f"{self.settings.get_transcription_model(provider_id)}"
        )

    def _activity_prepare_label(self) -> str:
        provider_id = self.settings.provider
        if provider_id == "gemini":
            return "上传 / 处理 Gemini 音频"
        return f"音频转写 · {self._transcription_route_name()}"

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

        provider_name = self._active_provider_name()
        model = self.settings.get_model(self.settings.provider)
        self.activity_model_desc = f"{provider_name} · {model}"

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

        self.activity_title.setText(f"{provider_name} 任务处理中")
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
        if percent >= 72 or "正在总结视频" in text or "总结转写文本" in text:
            return "inference"
        if percent >= 54:
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
        provider_name = self._active_provider_name()

        if new_stage == "upload":
            self.activity_title.setText("正在准备 AI 输入")
            if self.settings.provider == "gemini":
                self.activity_hint_label.setText(
                    "音频正在上传或由 Google Gemini 处理，完成后会自动进入模型分析。"
                )
            else:
                self.activity_hint_label.setText(
                    f"正在使用 {self._transcription_route_name()} 将音频转写为文本，完成后会提交给 {provider_name}。"
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
            self.activity_title.setText(f"{provider_name} 正在生成视频笔记")
            self.activity_hint_label.setText(
                f"已向 {provider_name} 提交内容，正在等待完整总结。程序仍在正常运行。"
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
        provider_name = self._active_provider_name()
        fallback_model = self.settings.get_model(self.settings.provider)
        model = self.activity_model_desc or f"{provider_name} · {fallback_model}"
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

        current_spec = PROVIDERS[self.settings.provider]
        if current_spec.supports_direct_audio:
            self.activity_route_label.setText(
                "音频路径：当前总结模型直接处理音频，无需独立转写步骤。"
            )
        else:
            self.activity_route_label.setText(
                f"转写模型：{self._transcription_route_name()}  →  "
                f"总结模型：{self._active_provider_name()} · "
                f"{self.settings.get_model(self.settings.provider)}"
            )


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
        self.activity_stage_name_labels["normalize"].setText("音频预处理")
        self.activity_stage_name_labels["upload"].setText(self._activity_prepare_label())
        self.activity_stage_name_labels["inference"].setText(
            f"{self._active_provider_name()} 生成摘要"
        )

        stages = ["source", "normalize", "upload", "inference"]
        current_index = (
            stages.index(self.activity_stage)
            if self.activity_stage in stages
            else len(stages)
        )

        for index, key in enumerate(stages):
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
        provider_name = self._active_provider_name()
        if seconds < 10:
            return f"{provider_name} 已接收生成请求，正在准备响应…"
        if seconds < 30:
            return f"正在等待 {provider_name} 返回完整总结。程序仍在正常运行，请稍候…"
        if seconds < 60:
            return "长视频分析通常需要更多时间；当前请求仍在处理中。"
        if seconds < 120:
            return "已等待较长时间。模型负载和网络状况可能影响响应速度，请保持程序开启。"
        return f"{provider_name} 请求仍在等待响应。若服务最终返回超时或错误，程序会明确提示；当前无需重复点击。"


    def _tick_activity(self) -> None:
        if not self.activity_running:
            return

        now = time.monotonic()
        self.activity_tick_count += 1
        total = max(0.0, now - self.activity_task_started)
        self.activity_elapsed_label.setText(f"总耗时 {self._format_clock(total)}")

        if self.activity_tick_count % 2 == 0:
            self.activity_pulse_bright = not self.activity_pulse_bright
            self.activity_pulse.setProperty("bright", self.activity_pulse_bright)
            self.activity_pulse.style().unpolish(self.activity_pulse)
            self.activity_pulse.style().polish(self.activity_pulse)

        if self.activity_stage == "inference":
            wait = max(0.0, now - self.activity_inference_started)
            self.activity_hint_label.setText(
                f"AI 已等待 {self._format_clock(wait)} · {self._activity_hint_for_wait(wait)}"
            )
        elif self.activity_stage == "upload":
            if self.settings.provider == "gemini":
                self.activity_hint_label.setText(
                    "Google Gemini 正在接收或处理上传音频；完成后会自动进入 AI 分析。"
                )
            else:
                self.activity_hint_label.setText(
                    f"{self._transcription_route_name()} 正在转写音频；完成后会自动进入 AI 总结。"
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

        friendly = classify_error(message)
        self.result_browser.setPlainText(
            f"{friendly.title}\n\n{friendly.summary}\n\n建议：{friendly.suggestion}"
        )
        FriendlyErrorDialog(
            friendly,
            theme=self.theme,
            log_path=self.latest_log,
            on_open_log=self.show_log,
            parent=self,
        ).exec()

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
        self._toast("Markdown 已复制到剪贴板", "success")

    def save_result(self) -> None:
        if not self.result_markdown:
            self._toast("当前还没有可以保存的总结结果。", "info")
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
            self._toast(f"已保存：{Path(path).name}", "success")

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
            self._toast(
                "任务仍在运行。为避免中断临时文件和云端清理，请等待任务完成后再关闭。",
                "warning",
                4200,
            )
            event.ignore()
            return
        if self.model_thread and self.model_thread.isRunning():
            self._toast("模型列表正在刷新，请等待几秒后再关闭。", "info")
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
