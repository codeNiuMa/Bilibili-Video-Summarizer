from __future__ import annotations
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

from downloader import MediaError, download_bilibili_audio, normalize_audio
from gemini_summarizer import GeminiError, summarize_audio

try:
    from gemini_summarizer import list_available_models
except ImportError:
    # 即使旧版 gemini_summarizer.py 还没加入“刷新模型”，也不影响主流程运行。
    def list_available_models(api_key: str) -> list[str]:
        raise GeminiError("当前 gemini_summarizer.py 尚未加入模型列表刷新功能。")
from settings import (
    DOWNLOAD_DIR,
    LOG_DIR,
    Settings,
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

# 仅作为接口刷新失败时的备用列表。
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]

# ---------- UI palette ----------
BG = ("#F4F6FA", "#0F1115")
SIDEBAR = ("#FFFFFF", "#15181E")
CARD = ("#FFFFFF", "#181C23")
CARD_ALT = ("#F8FAFC", "#1E232B")
BORDER = ("#E3E7EE", "#2A303A")
TEXT = ("#111827", "#F3F5F7")
MUTED = ("#667085", "#98A2B3")
ACCENT = "#4F7CFF"
ACCENT_HOVER = "#3D68E8"
SUCCESS = "#22A06B"
DANGER = "#E5484D"


class MainWindow(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        ctk.CTk.__init__(self)
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("B站视频总结工具")
        self.geometry("1180x820")
        self.minsize(920, 680)
        self.configure(fg_color=BG)

        self.settings = load_settings()
        self.api_key = load_api_key()
        if self.settings.appearance in {"light", "dark"}:
            ctk.set_appearance_mode(self.settings.appearance.capitalize())
        self.local_file = ""
        self.result = ""
        self.running = False
        self.log_lock = threading.Lock()
        self.latest_log = LOG_DIR / "latest_yt_dlp.log"

        self._build_ui()
        self._refresh_config_labels()

    # ================================================================
    # UI
    # ================================================================
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_workspace()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(
            self,
            width=250,
            corner_radius=0,
            fg_color=SIDEBAR,
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(9, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=22, pady=(26, 22))

        ctk.CTkLabel(
            brand,
            text="✦",
            width=34,
            height=34,
            corner_radius=10,
            fg_color=ACCENT,
            text_color="white",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(side="left")

        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=(11, 0))
        ctk.CTkLabel(
            brand_text,
            text="Bili Summary",
            anchor="w",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 17, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text,
            text="AI 视频笔记助手",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 11),
        ).pack(anchor="w", pady=(1, 0))

        ctk.CTkLabel(
            sidebar,
            text="连接状态",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 8))

        status_card = ctk.CTkFrame(
            sidebar,
            fg_color=CARD_ALT,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        status_card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 18))

        self.api_label = ctk.CTkLabel(
            status_card,
            text="",
            anchor="w",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.api_label.pack(fill="x", padx=14, pady=(12, 5))

        self.cookie_label = ctk.CTkLabel(
            status_card,
            text="",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 11),
        )
        self.cookie_label.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(
            sidebar,
            text="AI 模型",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 8))

        model_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        model_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        model_frame.grid_columnconfigure(0, weight=1)

        self.model_box = ctk.CTkComboBox(
            model_frame,
            values=MODELS,
            height=38,
            corner_radius=9,
            border_width=1,
            border_color=BORDER,
            fg_color=CARD_ALT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=CARD,
            text_color=TEXT,
            command=self.change_model,
            font=("Microsoft YaHei UI", 11),
        )
        self.model_box.set(self.settings.model)
        self.model_box.grid(row=0, column=0, sticky="ew")

        self.refresh_models_button = ctk.CTkButton(
            model_frame,
            text="↻",
            width=38,
            height=38,
            corner_radius=9,
            fg_color=CARD_ALT,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Arial", 18, "bold"),
            command=self.refresh_models,
        )
        self.refresh_models_button.grid(row=0, column=1, padx=(7, 0))

        options_card = ctk.CTkFrame(
            sidebar,
            fg_color=CARD_ALT,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        options_card.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))

        self.keep_download_var = ctk.BooleanVar(value=self.settings.keep_download)
        self.keep_download_switch = ctk.CTkSwitch(
            options_card,
            text="保留下载音频",
            variable=self.keep_download_var,
            command=self.change_keep_download,
            progress_color=ACCENT,
            button_color=("#FFFFFF", "#E5E7EB"),
            button_hover_color=("#FFFFFF", "#FFFFFF"),
            text_color=TEXT,
            font=("Microsoft YaHei UI", 11),
        )
        self.keep_download_switch.pack(fill="x", padx=14, pady=(13, 8))

        ctk.CTkButton(
            options_card,
            text="打开下载目录",
            height=30,
            corner_radius=8,
            fg_color="transparent",
            hover_color=BORDER,
            border_width=0,
            text_color=ACCENT,
            anchor="w",
            command=self.open_download_dir,
            font=("Microsoft YaHei UI", 11),
        ).pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkLabel(
            sidebar,
            text="设置",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 8))

        settings_group = ctk.CTkFrame(sidebar, fg_color="transparent")
        settings_group.grid(row=7, column=0, sticky="ew", padx=16)

        self.theme_var = ctk.BooleanVar(
            value=ctk.get_appearance_mode() == "Light"
        )

        self.theme_switch = ctk.CTkSwitch(
            settings_group,
            text="浅色模式",
            variable=self.theme_var,
            command=self.change_appearance,
            progress_color=ACCENT,
            button_color=("#FFFFFF", "#E5E7EB"),
            text_color=TEXT,
            font=("Microsoft YaHei UI", 11),
        )

        self.theme_switch.pack(
            fill="x",
            padx=8,
            pady=(0, 10),
        )

        self._sidebar_button(settings_group, "🔑  API Key", self.set_api_key).pack(
            fill="x", pady=(0, 6)
        )
        self._sidebar_button(settings_group, "🍪  Cookie", self.set_cookie).pack(
            fill="x", pady=(0, 6)
        )
        self._sidebar_button(settings_group, "⌁  下载日志", self.show_log).pack(
            fill="x"
        )

        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=10, column=0, sticky="sew", padx=22, pady=20)
        ctk.CTkLabel(
            footer,
            text="Simple v3 · 稳定流程",
            text_color=MUTED,
            anchor="w",
            font=("Microsoft YaHei UI", 10),
        ).pack(fill="x")
        ctk.CTkLabel(
            footer,
            text="yt-dlp  →  FFmpeg  →  Gemini",
            text_color=MUTED,
            anchor="w",
            font=("Consolas", 9),
        ).pack(fill="x", pady=(3, 0))

    def _sidebar_button(self, parent, text, command):
        return ctk.CTkButton(
            parent,
            text=text,
            height=36,
            corner_radius=9,
            fg_color="transparent",
            hover_color=CARD_ALT,
            border_width=0,
            text_color=TEXT,
            anchor="w",
            command=command,
            font=("Microsoft YaHei UI", 11),
        )

    def _build_workspace(self):
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=0, column=1, sticky="nsew", padx=26, pady=24)
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(4, weight=1)

        # Header
        header = ctk.CTkFrame(workspace, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_group,
            text="视频摘要",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 27, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_group,
            text="粘贴 B 站链接，或拖入本地音视频，让 Gemini 提炼核心内容。",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 12),
        ).pack(anchor="w", pady=(4, 0))

        self.status_pill = ctk.CTkFrame(
            header,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        self.status_pill.grid(row=0, column=1, sticky="e")
        self.status_dot = ctk.CTkLabel(
            self.status_pill,
            text="●",
            width=18,
            text_color=SUCCESS,
            font=("Arial", 12),
        )
        self.status_dot.pack(side="left", padx=(10, 1), pady=6)
        self.status_label = ctk.CTkLabel(
            self.status_pill,
            text="就绪",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 10),
        )
        self.status_label.pack(side="left", padx=(0, 11), pady=6)

        # Source card
        source_card = ctk.CTkFrame(
            workspace,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        source_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        source_card.grid_columnconfigure(0, weight=1)

        source_head = ctk.CTkFrame(source_card, fg_color="transparent")
        source_head.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        source_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            source_head,
            text="输入视频",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            source_head,
            text="清空",
            width=58,
            height=28,
            corner_radius=8,
            fg_color="transparent",
            hover_color=CARD_ALT,
            text_color=MUTED,
            command=self._clear_source,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=0, column=1, sticky="e")

        url_row = ctk.CTkFrame(source_card, fg_color="transparent")
        url_row.grid(row=1, column=0, sticky="ew", padx=20)
        url_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            url_row,
            height=44,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            fg_color=CARD_ALT,
            text_color=TEXT,
            placeholder_text="粘贴 B 站视频链接，例如 https://www.bilibili.com/video/BV...",
            placeholder_text_color=MUTED,
            font=("Microsoft YaHei UI", 11),
        )
        self.url_entry.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            url_row,
            text="粘贴",
            width=68,
            height=44,
            corner_radius=10,
            fg_color=CARD_ALT,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            command=self._paste_url,
            font=("Microsoft YaHei UI", 11),
        ).grid(row=0, column=1, padx=(8, 0))

        divider = ctk.CTkFrame(source_card, height=1, fg_color=BORDER)
        divider.grid(row=2, column=0, sticky="ew", padx=20, pady=15)

        self.drop_frame = ctk.CTkFrame(
            source_card,
            height=82,
            corner_radius=12,
            fg_color=CARD_ALT,
            border_width=1,
            border_color=BORDER,
        )
        self.drop_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.drop_frame.grid_propagate(False)
        self.drop_frame.grid_columnconfigure(1, weight=1)
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self.handle_drop)

        ctk.CTkLabel(
            self.drop_frame,
            text="＋",
            width=40,
            height=40,
            corner_radius=10,
            fg_color=("#EEF2FF", "#242B3A"),
            text_color=ACCENT,
            font=("Arial", 22),
        ).grid(row=0, column=0, rowspan=2, padx=(15, 12), pady=16)

        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            text="拖入本地音视频文件",
            anchor="w",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.file_label.grid(row=0, column=1, sticky="sw", pady=(16, 0))

        self.file_hint_label = ctk.CTkLabel(
            self.drop_frame,
            text="支持 m4s / mp3 / mp4 / m4a / wav 等常见格式",
            anchor="w",
            text_color=MUTED,
            font=("Microsoft YaHei UI", 10),
        )
        self.file_hint_label.grid(row=1, column=1, sticky="nw", pady=(1, 16))

        ctk.CTkButton(
            self.drop_frame,
            text="选择文件",
            width=90,
            height=34,
            corner_radius=9,
            fg_color="transparent",
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            command=self.choose_file,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=0, column=2, rowspan=2, padx=14)

        # Action / progress card
        action_card = ctk.CTkFrame(
            workspace,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        action_card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        action_card.grid_columnconfigure(0, weight=1)

        self.start_button = ctk.CTkButton(
            action_card,
            text="开始总结",
            height=46,
            corner_radius=11,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=("Microsoft YaHei UI", 13, "bold"),
            command=self.start,
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))

        progress_row = ctk.CTkFrame(action_card, fg_color="transparent")
        progress_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 15))
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(
            progress_row,
            height=7,
            corner_radius=4,
            fg_color=CARD_ALT,
            progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew")

        self.progress_percent_label = ctk.CTkLabel(
            progress_row,
            text="0%",
            width=42,
            text_color=MUTED,
            font=("Consolas", 10),
        )
        self.progress_percent_label.grid(row=0, column=1, padx=(9, 0))

        # Result card
        result_card = ctk.CTkFrame(
            workspace,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
        )
        result_card.grid(row=4, column=0, sticky="nsew")
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        result_head = ctk.CTkFrame(result_card, fg_color="transparent")
        result_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 10))
        result_head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            result_head,
            text="总结结果",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.copy_button = ctk.CTkButton(
            result_head,
            text="复制",
            width=66,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            hover_color=CARD_ALT,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            state="disabled",
            command=self.copy_result,
            font=("Microsoft YaHei UI", 10),
        )
        self.copy_button.grid(row=0, column=1, padx=(6, 0))

        self.save_button = ctk.CTkButton(
            result_head,
            text="保存 Markdown",
            width=108,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            hover_color=CARD_ALT,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            state="disabled",
            command=self.save_result,
            font=("Microsoft YaHei UI", 10),
        )
        self.save_button.grid(row=0, column=2, padx=(6, 0))

        self.result_box = ctk.CTkTextbox(
            result_card,
            wrap="word",
            corner_radius=10,
            border_width=0,
            fg_color=CARD_ALT,
            text_color=TEXT,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
            font=("Microsoft YaHei UI", 13),
            spacing1=3,
            spacing3=5,
        )
        self.result_box.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        text_widget = self.result_box._textbox

        text_widget.tag_configure(
            "h1",
            font=("Microsoft YaHei UI", 22, "bold"),
            spacing1=14,
            spacing3=8,
        )

        text_widget.tag_configure(
            "h2",
            font=("Microsoft YaHei UI", 18, "bold"),
            spacing1=12,
            spacing3=7,
        )

        text_widget.tag_configure(
            "h3",
            font=("Microsoft YaHei UI", 15, "bold"),
            spacing1=10,
            spacing3=6,
        )

        text_widget.tag_configure(
            "bold",
            font=("Microsoft YaHei UI", 13, "bold"),
        )

        text_widget.tag_configure(
            "bullet",
            lmargin1=18,
            lmargin2=35,
            spacing1=3,
            spacing3=3,
        )

        text_widget.tag_configure(
            "number",
            lmargin1=10,
            lmargin2=28,
            spacing1=6,
            spacing3=3,
        )

        text_widget.tag_configure(
            "quote",
            lmargin1=18,
            lmargin2=18,
            spacing1=4,
            spacing3=4,
        )

        text_widget.tag_configure(
            "code",
            font=("Consolas", 11),
        )
        self.result_box.insert(
            "1.0",
            "总结完成后，结果会显示在这里。\n\n提示：详细的 yt-dlp 下载过程可在左侧“下载日志”中查看。",
        )
        self.result_box.configure(text_color=MUTED)

    # ================================================================
    # UI helpers / settings
    # ================================================================
    def _refresh_config_labels(self):
        self.api_label.configure(
            text="●  API Key 已配置" if self.api_key else "●  API Key 未配置",
            text_color=SUCCESS if self.api_key else DANGER,
        )
        cookie = Path(self.settings.cookie_file).name if self.settings.cookie_file else "未使用"
        self.cookie_label.configure(text=f"Cookie：{cookie}")

    def _paste_url(self):
        try:
            value = self.clipboard_get().strip()
        except Exception:
            value = ""
        if value:
            self.local_file = ""
            self.file_label.configure(text="拖入本地音视频文件")
            self.file_hint_label.configure(text="支持 m4s / mp3 / mp4 / m4a / wav 等常见格式")
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, value)

    def _clear_source(self):
        self.url_entry.delete(0, "end")
        self.local_file = ""
        self.file_label.configure(text="拖入本地音视频文件")
        self.file_hint_label.configure(text="支持 m4s / mp3 / mp4 / m4a / wav 等常见格式")
        self._set_status("就绪", SUCCESS)

    def _set_status(self, text: str, color=SUCCESS):
        self.status_label.configure(text=text)
        self.status_dot.configure(text_color=color)

    def set_api_key(self):
        value = simpledialog.askstring(
            "Gemini API Key",
            "请输入 Gemini API Key：\n将保存在 ~/.bili_summarizer/api_key.txt",
            show="*",
            parent=self,
        )
        if value and value.strip():
            save_api_key(value)
            self.api_key = value.strip()
            self._refresh_config_labels()
            messagebox.showinfo("完成", "API Key 已保存。")
            self.refresh_models()

    def set_cookie(self):
        path = filedialog.askopenfilename(
            title="选择 Netscape 格式 Cookie 文件（可选）",
            filetypes=[("Cookie text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.settings.cookie_file = path
            save_settings(self.settings)
            self._refresh_config_labels()
        elif self.settings.cookie_file:
            if messagebox.askyesno("Cookie", "是否清除当前 Cookie 设置？"):
                self.settings.cookie_file = ""
                save_settings(self.settings)
                self._refresh_config_labels()

    def refresh_models(self):
        if not self.api_key:
            messagebox.showwarning("缺少 API Key", "请先配置 Gemini API Key。")
            return

        self.refresh_models_button.configure(state="disabled", text="…")
        self._set_status("刷新模型中", ACCENT)

        threading.Thread(
            target=self._refresh_models_worker,
            daemon=True,
        ).start()

    def _refresh_models_worker(self):
        try:
            models = list_available_models(self.api_key)
            self.after(0, self._apply_models, models)
        except Exception as exc:
            self.after(0, self._models_refresh_failed, str(exc))

    def _apply_models(self, models):
        self.refresh_models_button.configure(state="normal", text="↻")
        self.model_box.configure(values=models)

        current = self.settings.model
        if current in models:
            self.model_box.set(current)
        else:
            current = models[0]
            self.model_box.set(current)
            self.settings.model = current
            save_settings(self.settings)

        self._set_status(f"发现 {len(models)} 个模型", SUCCESS)

    def _models_refresh_failed(self, message):
        self.refresh_models_button.configure(state="normal", text="↻")
        self._set_status("模型刷新失败", DANGER)
        messagebox.showerror("刷新模型失败", message)

    def change_model(self, value: str):
        self.settings.model = value.strip()
        save_settings(self.settings)

    def change_keep_download(self):
        self.settings.keep_download = bool(self.keep_download_var.get())
        save_settings(self.settings)
        if self.settings.keep_download:
            self._set_status("将保留原始音频", SUCCESS)
        else:
            self._set_status("临时音频自动清理", SUCCESS)

    def change_appearance(self):
        if self.theme_var.get():
            mode = "Light"
            self.settings.appearance = "light"
        else:
            mode = "Dark"
            self.settings.appearance = "dark"

        ctk.set_appearance_mode(mode)
        save_settings(self.settings)

    def open_download_dir(self):
        import os
        import subprocess
        import sys

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(DOWNLOAD_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(DOWNLOAD_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(DOWNLOAD_DIR)])
        except Exception as exc:
            messagebox.showerror(
                "无法打开目录",
                f"请手动打开：\n{DOWNLOAD_DIR}\n\n{exc}",
            )

    # ================================================================
    # Input
    # ================================================================
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="选择本地音视频文件",
            filetypes=[("Media", "*" + " *".join(SUPPORTED_MEDIA)), ("All files", "*.*")],
        )
        if path:
            self._set_local_file(path)

    def handle_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        if not paths:
            return
        path = str(paths[0])
        if Path(path).suffix.lower() not in SUPPORTED_MEDIA:
            messagebox.showwarning("格式不支持", "请拖入常见音频或视频文件。")
            return
        self._set_local_file(path)

    def _set_local_file(self, path: str):
        self.local_file = path
        name = Path(path).name
        self.file_label.configure(text=name)
        self.file_hint_label.configure(text=path)
        self.url_entry.delete(0, "end")
        self._set_status("已选择本地文件", SUCCESS)

    # ================================================================
    # Progress / logs
    # ================================================================
    def _ui_progress(self, percent: int, text: str):
        self.after(0, lambda: self._apply_progress(percent, text))

    def _apply_progress(self, percent: int, text: str):
        percent = max(0, min(100, percent))
        self.progress.set(percent / 100)
        self.progress_percent_label.configure(text=f"{percent}%")
        self._set_status(text, ACCENT if percent < 100 else SUCCESS)

    def _write_log(self, line: str):
        with self.log_lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with self.latest_log.open("a", encoding="utf-8", errors="replace") as f:
                f.write(line.rstrip() + "\n")

    # ================================================================
    # Stable processing flow — intentionally kept unchanged
    # ================================================================
    def start(self):
        if self.running:
            return
        self.api_key = load_api_key()
        if not self.api_key:
            messagebox.showwarning("缺少 API Key", "请先在左侧配置 API Key。")
            return

        url = self.url_entry.get().strip()
        local = self.local_file.strip()
        if not url and not local:
            messagebox.showwarning("缺少输入", "请输入 B 站链接，或选择本地音视频文件。")
            return

        self.running = True
        self.start_button.configure(state="disabled", text="正在处理…")
        self.copy_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.result_box.configure(text_color=TEXT)
        self.result_box.delete("1.0", "end")
        self.result = ""
        self.progress.set(0)
        self.progress_percent_label.configure(text="0%")
        self._set_status("任务开始", ACCENT)
        self.latest_log.parent.mkdir(parents=True, exist_ok=True)
        self.latest_log.write_text(
            f"=== {datetime.now().isoformat(timespec='seconds')} ===\n",
            encoding="utf-8",
        )

        threading.Thread(
            target=self._worker,
            args=(url, local),
            daemon=True,
        ).start()

    def _worker(self, url: str, local: str):
        try:
            with tempfile.TemporaryDirectory(prefix="bili_summarizer_") as temp:
                temp_dir = Path(temp)
                if url:
                    source = download_bilibili_audio(
                        url=url,
                        output_dir=temp_dir / "download",
                        cookie_file=self.settings.cookie_file,
                        progress=self._ui_progress,
                        log=self._write_log,
                        keep_dir=DOWNLOAD_DIR if self.settings.keep_download else None,
                    )
                    audio = normalize_audio(
                        source,
                        temp_dir / "prepared",
                        self._ui_progress,
                        self._write_log,
                    )
                else:
                    audio = normalize_audio(
                        local,
                        temp_dir / "prepared",
                        self._ui_progress,
                        self._write_log,
                    )

                result = summarize_audio(
                    audio_path=audio,
                    api_key=self.api_key,
                    model=self.settings.model,
                    progress=self._ui_progress,
                )

            self.result = result
            self.after(0, self._show_result)
        except (MediaError, GeminiError) as exc:
            self.after(0, lambda e=str(exc): self._show_error(e))
        except Exception as exc:
            self._write_log(f"[unexpected] {type(exc).__name__}: {exc}")
            self.after(0, lambda e=str(exc): self._show_error(f"未预期错误：{e}"))
        finally:
            self.after(0, self._finish)

    def _insert_inline_markdown(self, text, base_tag=None):
        """
        处理一行中的：
        **粗体**
        `代码`
        """
        widget = self.result_box._textbox

        pattern = re.compile(r"(\*\*.*?\*\*|`.*?`)")
        pos = 0

        for match in pattern.finditer(text):
            normal = text[pos:match.start()]

            if normal:
                if base_tag:
                    widget.insert("end", normal, base_tag)
                else:
                    widget.insert("end", normal)

            token = match.group(0)

            if token.startswith("**"):
                content = token[2:-2]

                if base_tag:
                    widget.insert(
                        "end",
                        content,
                        (base_tag, "bold"),
                    )
                else:
                    widget.insert(
                        "end",
                        content,
                        "bold",
                    )

            elif token.startswith("`"):
                content = token[1:-1]

                if base_tag:
                    widget.insert(
                        "end",
                        content,
                        (base_tag, "code"),
                    )
                else:
                    widget.insert(
                        "end",
                        content,
                        "code",
                    )

            pos = match.end()

        tail = text[pos:]

        if tail:
            if base_tag:
                widget.insert("end", tail, base_tag)
            else:
                widget.insert("end", tail)

    def _render_markdown(self, markdown: str):
        widget = self.result_box._textbox

        self.result_box.delete("1.0", "end")

        lines = markdown.replace("\r\n", "\n").split("\n")

        for line in lines:
            stripped = line.strip()

            # 空行
            if not stripped:
                widget.insert("end", "\n")
                continue

            # Markdown 分隔线
            if stripped in {"---", "***", "___"}:
                widget.insert(
                    "end",
                    "────────────────────────────────────\n\n",
                )
                continue

            # 标题
            if stripped.startswith("### "):
                self._insert_inline_markdown(
                    stripped[4:],
                    "h3",
                )
                widget.insert("end", "\n")
                continue

            if stripped.startswith("## "):
                self._insert_inline_markdown(
                    stripped[3:],
                    "h2",
                )
                widget.insert("end", "\n")
                continue

            if stripped.startswith("# "):
                self._insert_inline_markdown(
                    stripped[2:],
                    "h1",
                )
                widget.insert("end", "\n")
                continue

            # 无序列表
            match = re.match(r"^\s*[-*]\s+(.+)$", line)

            if match:
                widget.insert("end", "• ", "bullet")
                self._insert_inline_markdown(
                    match.group(1),
                    "bullet",
                )
                widget.insert("end", "\n")
                continue

            # 有序列表
            match = re.match(r"^\s*(\d+)\.\s+(.+)$", line)

            if match:
                widget.insert(
                    "end",
                    f"{match.group(1)}. ",
                    "number",
                )

                self._insert_inline_markdown(
                    match.group(2),
                    "number",
                )

                widget.insert("end", "\n")
                continue

            # 引用
            if stripped.startswith("> "):
                widget.insert("end", "│ ", "quote")

                self._insert_inline_markdown(
                    stripped[2:],
                    "quote",
                )

                widget.insert("end", "\n")
                continue

            # 普通正文
            self._insert_inline_markdown(line)

            widget.insert("end", "\n")

    def _show_result(self):
        self.result_box.configure(text_color=TEXT)

        self._render_markdown(self.result)

        self.copy_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self._set_status("总结完成", SUCCESS)

    def _show_error(self, message: str):
        self._set_status("处理失败", DANGER)
        self.result_box.configure(text_color=TEXT)
        self.result_box.delete("1.0", "end")
        self.result_box.insert(
            "1.0",
            f"❌ {message}\n\n下载相关详细信息：\n{self.latest_log}",
        )
        messagebox.showerror("处理失败", message)

    def _finish(self):
        self.running = False
        self.start_button.configure(state="normal", text="开始总结")

    # ================================================================
    # Result / log actions
    # ================================================================
    def show_log(self):
        win = ctk.CTkToplevel(self)
        win.title("yt-dlp 下载日志")
        win.geometry("900x600")
        win.configure(fg_color=BG)

        shell = ctk.CTkFrame(
            win,
            fg_color=CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )
        shell.pack(fill="both", expand=True, padx=16, pady=16)

        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(
            header,
            text="下载日志",
            text_color=TEXT,
            font=("Microsoft YaHei UI", 14, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=str(self.latest_log),
            text_color=MUTED,
            font=("Consolas", 9),
        ).pack(side="right")

        box = ctk.CTkTextbox(
            shell,
            wrap="none",
            corner_radius=8,
            fg_color=CARD_ALT,
            text_color=TEXT,
            font=("Consolas", 11),
        )
        box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        try:
            text = self.latest_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = "暂时没有下载日志。"
        box.insert("1.0", text)
        box.configure(state="disabled")

    def copy_result(self):
        if not self.result:
            return
        self.clipboard_clear()
        self.clipboard_append(self.result)
        self._set_status("已复制结果", SUCCESS)

    def save_result(self):
        if not self.result:
            messagebox.showinfo("提示", "当前还没有总结结果。")
            return
        path = filedialog.asksaveasfilename(
            title="保存 Markdown",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
            initialfile=f"bili_summary_{datetime.now():%Y%m%d_%H%M%S}.md",
        )
        if path:
            Path(path).write_text(self.result, encoding="utf-8")
            self._set_status("Markdown 已保存", SUCCESS)


def run():
    app = MainWindow()
    app.mainloop()
