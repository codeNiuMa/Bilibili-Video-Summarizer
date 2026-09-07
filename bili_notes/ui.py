from __future__ import annotations

import sys
from pathlib import Path

from .qt_compat import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDesktopServices,
    QDialog,
    QFileDialog,
    QFont,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)

from .core import (
    DEFAULT_MODEL,
    MEDIA_EXTENSIONS,
    TEXT_EXTENSIONS,
    MODES,
    STYLES,
    Cancelled,
    CancelToken,
    Request,
    Settings,
    Store,
    TaskError,
)
from .credentials import Credentials
from .pipeline import Pipeline

THEME = """
QWidget { color: #263f3b; font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog { background: #f6f7f3; }
QFrame#sidebar { background: #eaf0e9; border-right: 1px solid #dbe3db; }
QLabel#brand { font-size: 25px; font-weight: 700; color: #173f37; }
QLabel#hero { font-size: 28px; font-weight: 700; }
QLabel#eyebrow { color: #47836c; font-size: 11px; font-weight: 700; }
QLabel#muted { color: #718079; }
QLabel#badge { color: #28765b; background: #e3eee4; padding: 7px 12px; border-radius: 12px; }
QFrame#card { background: white; border: 1px solid #dfe6dd; border-radius: 14px; }
QPushButton { background: #fff; border: 1px solid #d3dfd5; border-radius: 8px; padding: 9px 15px; }
QPushButton:hover { background: #e7eee6; border-color: #8eae99; }
QPushButton:disabled { color: #96a39a; background: #eef1eb; border-color: #e1e7df; }
QPushButton#primary { background: #24664e; color: white; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #194e3b; }
QPushButton#primary:disabled { background: #99b2a2; }
QLineEdit, QComboBox, QSpinBox { background: #fbfcf9; border: 1px solid #d9e2d8; border-radius: 8px; padding: 10px; selection-background-color: #d3e9d9; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #47876a; }
QComboBox::drop-down { border: none; width: 23px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dcebdd; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 13px 8px; margin: 3px 0; border-radius: 8px; }
QListWidget::item:selected { background: #d4e3d3; color: #204c3e; }
QListWidget::item:hover { background: #dfe9dc; }
QTextBrowser { background: #fff; border: none; padding: 18px; font-size: 15px; selection-background-color: #cee5d5; }
QTabWidget::pane { border: 1px solid #dfe6dd; background: white; border-radius: 8px; }
QTabBar::tab { padding: 12px 20px; color: #78867d; background: transparent; }
QTabBar::tab:selected { color: #23624c; border-bottom: 3px solid #23624c; font-weight: 700; }
QProgressBar { border: none; background: #dfe9de; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #438765; border-radius: 3px; }
QSplitter::handle { background: #f6f7f3; width: 12px; }
QToolTip { background: #244e3e; color: white; border: none; padding: 6px; }
"""
_assets = Path(__file__).with_name("assets").as_posix()
THEME += f"""
QComboBox {{ padding-right: 28px; }}
QComboBox::down-arrow {{ image: url("{_assets}/chevron-down.svg"); width: 12px; height: 8px; }}
QSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: none; }}
QSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: none; }}
QSpinBox::up-arrow {{ image: url("{_assets}/chevron-up.svg"); width: 12px; height: 8px; }}
QSpinBox::down-arrow {{ image: url("{_assets}/chevron-down.svg"); width: 12px; height: 8px; }}
"""


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


class Reader(QTextBrowser):
    """Render Markdown without loading embedded remote/local media."""

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.anchorClicked.connect(self.open_link)
        self.document().setDefaultStyleSheet(
            "h1 {font-size:24px;color:#244e3d} h2 {font-size:18px;color:#24664e} p,li {line-height:155%} blockquote {color:#728275}"
        )

    def loadResource(self, resource_type, url):
        return None

    def open_link(self, url):
        if url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)

    def markdown(self, value):
        self.document().setMarkdown(
            value,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML,
        )
        block = self.document().begin()
        while block.isValid():
            cursor = QTextCursor(block)
            formatting = block.blockFormat()
            formatting.setLineHeight(145, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            formatting.setBottomMargin(8)
            if formatting.headingLevel():
                formatting.setTopMargin(14)
                formatting.setBottomMargin(10)
            cursor.setBlockFormat(formatting)
            block = block.next()
        self.setTextCursor(QTextCursor(self.document()))
        self.verticalScrollBar().setValue(0)


class Job(QThread):
    progress = Signal(str, int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, store, settings, request, key, parent=None):
        super().__init__(parent)
        self.store, self.settings, self.request, self.key = store, settings, request, key
        self.token = CancelToken()

    def run(self):
        try:
            pipeline = Pipeline(self.store, self.settings, self.token, self.progress.emit)
            self.completed.emit(pipeline.run(self.request, self.key))
        except Cancelled as exc:
            self.cancelled.emit(str(exc))
        except TaskError as exc:
            self.failed.emit(str(exc))
        except OSError:
            self.failed.emit("本地文件读写失败，请检查文件权限、数据目录及剩余磁盘空间。")
        except Exception:
            self.failed.emit("处理失败，请检查素材格式和依赖版本后重试。未完成任务不会记为成功。")
        finally:
            self.key = ""


class ModelJob(QThread):
    models = Signal(list)
    failed = Signal(str)

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key

    def run(self):
        from google import genai
        from .gemini import explain_error

        try:
            with genai.Client(
                api_key=self.key, http_options={"timeout": 20000, "retry_options": {"attempts": 1}}
            ) as client:
                models = [
                    m.name.removeprefix("models/")
                    for m in client.models.list()
                    if m.name
                    and "generateContent" in (m.supported_actions or [])
                    and "gemini" in m.name
                ]
            self.models.emit(sorted(models))
        except Exception as exc:
            self.failed.emit(explain_error(exc))
        finally:
            self.key = ""


class SettingsDialog(QDialog):
    def __init__(self, store, credentials, parent):
        super().__init__(parent)
        self.store, self.credentials = store, credentials
        self.model_job = None
        self.setWindowTitle("模型与应用设置")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(label("连接你的 Gemini", "brand"))
        layout.addWidget(
            label(
                "Google AI Pro 订阅与 API 用量分别管理。请使用 AI Studio 的 API Key。\n刷新列表只读取可见模型；实际调用额度与音频支持以 API 项目为准。",
                "muted",
                True,
            )
        )
        form = QFormLayout()
        form.setVerticalSpacing(14)
        saved = store.settings()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("已配置，留空保留" if credentials.get() else "粘贴 API Key")
        form.addRow("API Key", self.key)
        self.remember = QCheckBox("记住密钥（存入系统凭据库）")
        form.addRow("", self.remember)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(list(dict.fromkeys([saved.model, DEFAULT_MODEL])))
        form.addRow("模型 ID", self.model)
        self.refresh = button("验证连接并刷新模型列表", self.fetch_models)
        form.addRow("", self.refresh)
        self.cookies = QLineEdit(saved.cookies)
        self.cookies.setPlaceholderText("可选：Netscape 格式 cookies.txt")
        cookie_row = QHBoxLayout()
        cookie_row.addWidget(self.cookies)
        cookie_row.addWidget(button("选择", self.choose_cookies))
        form.addRow("B 站 Cookie", cookie_row)
        self.ffmpeg = QLineEdit(saved.ffmpeg)
        self.ffmpeg.setPlaceholderText("留空自动使用系统或随依赖安装的 FFmpeg")
        form.addRow("FFmpeg 路径", self.ffmpeg)
        self.chunk = QSpinBox()
        self.chunk.setRange(60, 900)
        self.chunk.setSingleStep(60)
        self.chunk.setSuffix(" 秒")
        self.chunk.setValue(saved.chunk_seconds)
        form.addRow("音频分段", self.chunk)
        layout.addLayout(form)
        self.message = label("仅在本次会话使用时，密钥不会写入配置文件。", "muted", True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        actions.addWidget(button("移除已保存密钥", self.forget))
        actions.addStretch()
        self.save_button = button("保存设置", self.save, True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def choose_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Netscape Cookie 文件", "", "Cookie (*.txt);;所有文件 (*)"
        )
        if path:
            self.cookies.setText(path)

    def fetch_models(self):
        key = self.key.text().strip() or self.credentials.get()
        if not key:
            self.message.setText("请先填写 API Key。")
            return
        self.refresh.setEnabled(False)
        self.save_button.setEnabled(False)
        self.message.setText("正在连接 Gemini…")
        self.model_job = ModelJob(key, self)
        self.model_job.models.connect(self.got_models)
        self.model_job.failed.connect(self.message.setText)
        self.model_job.finished.connect(self.model_finished)
        self.model_job.start()

    def got_models(self, values):
        current = self.model.currentText()
        self.model.clear()
        self.model.addItems(list(dict.fromkeys([current, *values])))
        self.message.setText(
            f"连接成功，读取到 {len(values)} 个生成模型。请为音频任务选择支持音频输入的模型。"
        )

    def model_finished(self):
        self.refresh.setEnabled(True)
        self.save_button.setEnabled(True)
        self.model_job.deleteLater()
        self.model_job = None

    def forget(self):
        try:
            self.credentials.forget()
            self.key.clear()
            self.key.setPlaceholderText("粘贴 API Key")
            self.message.setText(
                "已移除应用保存的密钥。若设置了 GEMINI_API_KEY 环境变量，它仍然生效。"
            )
        except Exception:
            self.message.setText("无法访问系统凭据库，请在系统凭据管理器中移除 bili-notes 项。")

    def save(self):
        model = self.model.currentText().strip().removeprefix("models/")
        if not model:
            self.message.setText("请填写模型 ID。")
            return
        try:
            if key := self.key.text().strip():
                self.credentials.set(key, self.remember.isChecked())
            self.store.save_settings(
                Settings(
                    model,
                    self.cookies.text().strip(),
                    self.ffmpeg.text().strip(),
                    self.chunk.value(),
                )
            )
        except RuntimeError as exc:
            self.message.setText(str(exc))
            return
        except Exception:
            self.message.setText("设置保存失败，请检查数据目录或取消记住密钥后重试。")
            return
        self.accept()

    def reject(self):
        if self.model_job is not None:
            self.message.setText("正在验证连接，请等待请求结束后关闭。")
            return
        super().reject()

    def closeEvent(self, event):
        if self.model_job is not None:
            event.ignore()
        else:
            super().closeEvent(event)


class Window(QMainWindow):
    def __init__(self, store=None, credentials=None):
        super().__init__()
        self.store, self.credentials = store or Store(), credentials or Credentials()
        self.job = None
        self.result = None
        self.close_when_done = False
        self.setWindowTitle("Bili Notes · B 站视频笔记")
        self.resize(1240, 900)
        self.setMinimumSize(1000, 740)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(242)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 20, 24)
        side.setSpacing(16)
        side.addWidget(label("Bili Notes", "brand"))
        side.addWidget(label("把长视频，留成好笔记。", "muted"))
        self.new_button = button("＋  新建笔记", self.new_note, True)
        side.addWidget(self.new_button)
        side.addSpacing(14)
        side.addWidget(label("笔记库  /  LIBRARY", "eyebrow"))
        self.history = QListWidget()
        self.history.itemClicked.connect(self.open_history)
        side.addWidget(self.history, 1)
        self.history_empty = label("还没有笔记\n完成的总结会自动保存在这里。", "muted", True)
        side.addWidget(self.history_empty)
        self.settings_button = button("模型与设置", self.settings_dialog)
        side.addWidget(self.settings_button)
        self.clear_button = button("清理处理缓存", self.clear_cache)
        side.addWidget(self.clear_button)
        side.addWidget(label("原始文件保持完整\n笔记与缓存保存在本地", "muted", True))
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(32, 28, 32, 22)
        content.setSpacing(16)
        outer.addLayout(content, 1)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label("VIDEO TO KNOWLEDGE", "eyebrow"))
        heading.addWidget(label("少看一点，记住更多。", "hero"))
        top.addLayout(heading, 1)
        self.badge = label("Gemini · 待配置", "badge")
        top.addWidget(self.badge)
        content.addLayout(top)
        content.addWidget(
            label(
                "粘贴 B 站链接，或拖入本地音视频与字幕。把核心内容变成可回看的笔记。", "muted", True
            )
        )
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        card_layout.addWidget(label("01  添加素材", "eyebrow"))
        source_row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setPlaceholderText("粘贴 bilibili.com / b23.tv 链接或 BV 号")
        self.source.returnPressed.connect(self.start_job)
        source_row.addWidget(self.source, 1)
        self.file_button = button("选择本地文件", self.choose_file)
        source_row.addWidget(self.file_button)
        card_layout.addLayout(source_row)
        options = QHBoxLayout()
        self.mode = QComboBox()
        for value, text in MODES.items():
            self.mode.addItem(text, value)
        self.mode.setMinimumWidth(260)
        self.style = QComboBox()
        for value, text in STYLES.items():
            self.style.addItem(text, value)
        self.style.setCurrentIndex(1)
        options.addWidget(self.mode, 2)
        options.addWidget(self.style, 1)
        self.start_button = button("生成笔记  →", self.start_job, True)
        options.addWidget(self.start_button)
        self.cancel_button = button("取消", self.cancel_job)
        self.cancel_button.setEnabled(False)
        options.addWidget(self.cancel_button)
        card_layout.addLayout(options)
        card_layout.addWidget(
            label(
                "智能模式优先使用字幕；无字幕时上传音频给 Gemini。完整转写模式会额外生成逐字稿。",
                "muted",
                True,
            )
        )
        content.addWidget(card)
        status_row = QHBoxLayout()
        self.status = label("准备就绪", "eyebrow")
        self.detail = label("选择素材后即可开始", "muted")
        status_row.addWidget(self.status)
        status_row.addStretch()
        status_row.addWidget(self.detail)
        content.addLayout(status_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        self.progress.setFixedHeight(6)
        content.addWidget(self.progress)
        self.tabs = QTabWidget()
        self.summary = Reader()
        self.transcript = Reader()
        self.log = Reader()
        self.tabs.addTab(self.summary, "内容笔记")
        self.tabs.addTab(self.transcript, "字幕 / 逐字稿")
        self.tabs.addTab(self.log, "处理记录")
        content.addWidget(self.tabs, 1)
        footer = QHBoxLayout()
        self.stats = label("笔记支持 Markdown 导出", "muted")
        footer.addWidget(self.stats, 1)
        self.copy_button = button("复制笔记", self.copy)
        self.export_button = button("导出…", self.export)
        footer.addWidget(self.copy_button)
        footer.addWidget(self.export_button)
        content.addLayout(footer)
        self.refresh_history()
        self.update_badge()
        self.new_note()

    def new_note(self):
        if self.job is not None:
            return
        self.result = None
        self.source.clear()
        self.summary.markdown(
            "\n# 让每次观看，都有收获。\n\n从一个视频链接开始，生成结构清晰、方便回顾的笔记。\n\n---\n\n### 更快获取内容\n优先读取视频字幕；没有字幕时，自动提取音频。\n\n### 按你的方式整理\n精简速览、详细笔记，或提炼成行动清单。\n\n### 把知识留在手边\n历史自动保存，随时复制或导出 Markdown。"
        )
        self.transcript.setPlainText(
            "使用字幕或完整转写模式后，原文会显示在这里。\n直接音频总结模式不生成逐字稿。"
        )
        self.log.clear()
        self.last_log = None
        self.copy_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setText("准备就绪")
        self.detail.setText("选择素材后即可开始")
        self.stats.setText("笔记支持 Markdown 导出")
        self.tabs.setCurrentIndex(0)

    def update_badge(self):
        self.badge.setText("Gemini · 已配置" if self.credentials.get() else "Gemini · 待配置")
        self.badge.setToolTip(self.store.settings().model)

    def settings_dialog(self):
        SettingsDialog(self.store, self.credentials, self).exec()
        self.update_badge()

    def choose_file(self):
        extensions = " ".join("*" + x for x in sorted(MEDIA_EXTENSIONS | TEXT_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音视频或字幕", "", f"支持的素材 ({extensions});;所有文件 (*)"
        )
        if path:
            self.source.setText(path)

    def start_job(self):
        if self.job is not None:
            return
        if not self.source.text().strip():
            self.detail.setText("请先粘贴链接或选择素材。")
            self.source.setFocus()
            return
        key = self.credentials.get()
        if not key:
            self.settings_dialog()
            key = self.credentials.get()
            if not key:
                return
        request = Request(self.source.text(), self.mode.currentData(), self.style.currentData())
        self.result = None
        self.copy_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.summary.markdown(
            "# 正在整理你的笔记…\n\n可以在「处理记录」查看进度。完成的片段会自动缓存。"
        )
        self.transcript.clear()
        self.log.clear()
        self.last_log = None
        self.progress.setValue(0)
        self.stats.setText("处理中 · 取消后可重新开始并复用完成片段")
        self.job = Job(self.store, self.store.settings(), request, key, self)
        self.job.progress.connect(self.on_progress)
        self.job.completed.connect(self.show_result)
        self.job.failed.connect(self.on_failure)
        self.job.cancelled.connect(self.on_cancelled)
        self.job.finished.connect(self.on_finished)
        self.busy(True)
        self.job.start()

    def busy(self, value):
        for widget in (
            self.start_button,
            self.new_button,
            self.settings_button,
            self.file_button,
            self.clear_button,
            self.source,
            self.mode,
            self.style,
            self.history,
        ):
            widget.setEnabled(not value)
        self.cancel_button.setEnabled(value)

    def on_progress(self, stage, percent, message):
        self.status.setText(stage)
        self.detail.setText(message)
        if percent >= 0:
            self.progress.setValue(max(self.progress.value(), percent))
        line = f"{stage} · {message}"
        if line != getattr(self, "last_log", None):
            self.log.insertPlainText(line + "\n")
            self.last_log = line

    def show_result(self, result):
        self.result = result
        self.summary.markdown(result.markdown())
        self.transcript.setPlainText(
            result.transcript
            or "本次采用直接音频总结，没有生成逐字稿。需要全文时请选择“完整转写”。"
        )
        self.copy_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.stats.setText(
            f"API 调用 {result.api_calls} · 缓存命中 {result.cached_calls} · Token {result.prompt_tokens:,} 入 / {result.output_tokens:,} 出"
        )
        self.tabs.setCurrentIndex(0)
        self.refresh_history()

    def on_failure(self, text):
        self.on_progress("未完成", -1, "请查看说明后重试")
        self.summary.setPlainText("本次任务未完成\n\n" + text)
        self.log.insertPlainText(text + "\n")
        self.stats.setText("已完成片段已缓存，可使用相同设置重试")

    def on_cancelled(self, text):
        self.status.setText("已取消")
        self.detail.setText("临时文件已清理")
        self.summary.setPlainText(text)
        self.stats.setText("重新开始时复用已完成片段")

    def on_finished(self):
        self.job.deleteLater()
        self.job = None
        self.busy(False)
        if self.close_when_done:
            self.close()

    def cancel_job(self):
        if self.job is not None:
            self.job.token.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消")
            self.detail.setText("等待当前网络请求结束并清理文件…")

    def refresh_history(self):
        self.history.clear()
        for result in self.store.history():
            item = QListWidgetItem(result.title[:24] + "\n" + result.created[:10])
            item.setToolTip(result.title)
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.history.addItem(item)
        self.history_empty.setVisible(self.history.count() == 0)

    def open_history(self, item):
        result = item.data(Qt.ItemDataRole.UserRole)
        self.show_result(result)
        self.source.setText(result.source)
        self.status.setText("历史笔记")
        self.detail.setText(result.created[:19].replace("T", " "))
        self.progress.setValue(100)

    def copy(self):
        if self.result:
            QApplication.clipboard().setText(self.result.markdown())
            self.detail.setText("笔记已复制")

    def export(self):
        if not self.result:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "导出笔记", "视频笔记.md", "Markdown 笔记 (*.md);;逐字稿 (*.txt)"
        )
        if not path:
            return
        text = self.result.transcript if "*.txt" in selected else self.result.markdown()
        if not text:
            QMessageBox.information(self, "没有逐字稿", "本次未生成逐字稿，请导出 Markdown 笔记。")
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
            self.detail.setText("导出完成")
        except OSError:
            QMessageBox.warning(self, "导出失败", "请检查目标文件是否被占用，或选择其他目录。")

    def clear_cache(self):
        try:
            self.store.clear_cache()
            self.detail.setText("处理缓存已清理，历史笔记仍保留。")
        except OSError:
            self.detail.setText("缓存清理失败，请检查目录权限。")

    def dragEnterEvent(self, event):
        if self.job is None and (event.mimeData().hasUrls() or event.mimeData().hasText()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.job is not None:
            return
        urls = event.mimeData().urls()
        if len(urls) > 1:
            self.detail.setText("每次处理一个文件，请单独拖入。")
            return
        self.source.setText(
            (urls[0].toLocalFile() if urls[0].isLocalFile() else urls[0].toString())
            if urls
            else event.mimeData().text()
        )
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.job is not None:
            self.close_when_done = True
            self.cancel_job()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(THEME)
    window = Window()
    window.show()
    # Used only by automated local smoke checks, not a fake processing mode.
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(600, window.close)
    sys.exit(app.exec())
