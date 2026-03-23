# -*- coding: utf-8 -*-
import customtkinter as ctk
import re
from tkinter import filedialog, messagebox
import threading
import subprocess
import os
import glob
from google import genai
from tkinterdnd2 import DND_FILES, TkinterDnD
import yt_dlp  # 🌟 新增：强大的音视频下载库
import shutil  # 🌟 新增：用于文件复制和移动
import customtkinter as ctk

# ==========================================
# 🔑 在这里填入你的 Gemini API Key
# ==========================================
# MY_API_KEY = ""  # <-- 请将你的 Key 粘贴在双引号中间
MODEL_NAME = 'gemini-3.1-flash-lite-preview'

# ==========================================
# ⚙️ 全局配置目录设定
# ==========================================
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".bili_summarizer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "api_key.txt")


# --- 全局主题设置 ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class TkinterDnD_CTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class VideoSummarizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("B站省流神器 - AI 总结助理")
        self.root.geometry("1000x800")  # 稍微加宽了一点点
        self.root.minsize(650, 600)

        self.downloaded_file_path = None
        self.api_key = self.load_api_key()

        # --- 主容器 ---
        self.main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=30, pady=20)

        # --- 🌟 顶部标题与设置区 ---
        self.top_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.top_frame.pack(fill="x", pady=(0, 15))

        self.title_label = ctk.CTkLabel(self.top_frame, text="✨ B站长视频摘要提取",
                                        font=("Microsoft YaHei", 24, "bold"))
        self.title_label.pack(side="left")

        # 1. 配置按钮 (靠最右)
        self.settings_btn = ctk.CTkButton(
            self.top_frame,
            text="⚙️ 配置 API Key",
            command=self.prompt_api_key,
            width=120,
            height=32,
            fg_color="#34495E",
            hover_color="#2C3E50",
            font=("Microsoft YaHei", 12, "bold")
        )
        self.settings_btn.pack(side="right")

        # 2. 状态标签 (紧贴按钮左侧)
        self.api_status_label = ctk.CTkLabel(
            self.top_frame,
            text="",
            font=("Microsoft YaHei", 12, "bold")
        )
        self.api_status_label.pack(side="right", padx=15)

        # --- 🌐 网络链接提取区 ---
        self.url_label = ctk.CTkLabel(self.main_frame, text="🔗 方式一：输入 B 站视频链接直接解析",
                                      font=("Microsoft YaHei", 13, "bold"))
        self.url_label.pack(anchor="w", pady=(0, 5))

        self.url_entry = ctk.CTkEntry(
            self.main_frame,
            height=40,
            placeholder_text="粘贴 B 站视频链接 (例如: https://www.bilibili.com/video/BV...)",
            font=("Arial", 13)
        )
        self.url_entry.pack(fill="x", pady=(0, 20))

        # --- 📁 本地拖拽与文件选择区 ---
        self.local_label = ctk.CTkLabel(self.main_frame, text="📁 方式二：或者处理本地音频文件",
                                        font=("Microsoft YaHei", 13, "bold"))
        self.local_label.pack(anchor="w", pady=(0, 5))

        self.file_path_var = ctk.StringVar()
        self.file_path_var.set("将音频文件拖拽到此虚线框内，或点击右侧按钮选择 👇")

        self.drop_frame = ctk.CTkFrame(self.main_frame, fg_color=("gray85", "gray20"), corner_radius=15, border_width=2,
                                       border_color="#555555")
        self.drop_frame.pack(fill="x", pady=(0, 20), ipadx=10, ipady=15)

        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            textvariable=self.file_path_var,
            text_color="gray",
            font=("Microsoft YaHei", 13),
            wraplength=450
        )
        self.file_label.pack(side="left", padx=20, expand=True, fill="x")

        self.file_btn = ctk.CTkButton(
            self.drop_frame,
            text="浏览文件",
            command=self.select_file,
            fg_color="#2FA572",
            hover_color="#1D7A50",
            font=("Microsoft YaHei", 13, "bold"),
            width=80,
            height=35
        )
        self.file_btn.pack(side="right", padx=15)

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_drop)

        # --- 动作按钮区 ---
        self.action_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", pady=(0, 20))

        self.process_btn = ctk.CTkButton(
            self.action_frame,
            text="🚀 开始提取核心摘要",
            command=self.start_processing,
            height=50,
            font=("Microsoft YaHei", 16, "bold"),
            corner_radius=8
        )
        self.process_btn.pack(side="left", fill="x", expand=True, padx=(0, 15))

        self.delete_btn = ctk.CTkButton(
            self.action_frame,
            text="🗑️ 删除本地文件",
            command=self.delete_local_files,
            fg_color="#E74C3C",
            hover_color="#C0392B",
            height=50,
            width=140,
            font=("Microsoft YaHei", 14, "bold"),
            corner_radius=8
        )
        self.delete_btn.pack(side="right")

        # --- 输出结果区 ---
        self.result_label = ctk.CTkLabel(self.main_frame, text="📝 分析结果：", font=("Microsoft YaHei", 14, "bold"))
        self.result_label.pack(anchor="w", pady=(0, 5))

        self.result_text = ctk.CTkTextbox(
            self.main_frame,
            wrap="word",
            font=("Microsoft YaHei", 14),
            corner_radius=10,
            border_width=1,
            border_color="#444444"
        )
        self.result_text.pack(fill="both", expand=True)

        self.result_text._textbox.tag_config("bold", font=("Microsoft YaHei", 14, "bold"))
        self.result_text._textbox.tag_config("h1", font=("Microsoft YaHei", 18, "bold"))
        self.result_text._textbox.tag_config("h2", font=("Microsoft YaHei", 16, "bold"))

        # 初始化状态显示
        self.update_api_status_ui()

        if not self.api_key:
            self.root.after(500, self.prompt_api_key)

    # ==========================================
    # 🌟 API 状态管理逻辑
    # ==========================================
    def update_api_status_ui(self):
        """刷新 API 状态标签的显示内容和颜色"""
        if self.api_key:
            self.api_status_label.configure(text="● 已配置", text_color="#2ECC71")  # 绿色
        else:
            self.api_status_label.configure(text="● 未配置", text_color="#E74C3C")  # 红色

    def load_api_key(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def save_api_key(self, key):
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
        self.api_key = key.strip()
        self.update_api_status_ui()  # 保存后立即更新状态

    def prompt_api_key(self):
        dialog = ctk.CTkInputDialog(
            text="请输入您的 Gemini API Key:\n(您的 Key 将安全保存在本地路径:\n" + CONFIG_FILE + ")",
            title="⚙️ 配置 API Key"
        )
        key_input = dialog.get_input()

        if key_input and key_input.strip():
            self.save_api_key(key_input)
            messagebox.showinfo("成功", "API Key 已成功保存并启用！")
        elif not self.api_key:
            messagebox.showwarning("警告", "未检测到有效的 API Key。")
        self.update_api_status_ui()

    # ==========================================
    # 处理逻辑
    # ==========================================
    def handle_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]

        valid_extensions = ('.m4s', '.mp3', '.wav', '.aac')
        if file_path.lower().endswith(valid_extensions):
            self.file_path_var.set(file_path)
            self.url_entry.delete(0, ctk.END)
        else:
            messagebox.showwarning("格式不支持", "请拖入常见的音频文件。")

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("Audio Files", "*.m4s *.mp3 *.wav *.aac"), ("All Files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.url_entry.delete(0, ctk.END)

    def delete_local_files(self):
        files_to_delete = []
        local_file = self.file_path_var.get()
        if not "拖拽到此" in local_file and local_file:
            files_to_delete.append(local_file)
            if local_file.lower().endswith('.m4s'):
                mp3_path = local_file.rsplit('.', 1)[0] + ".mp3"
                files_to_delete.append(mp3_path)
        if self.downloaded_file_path:
            files_to_delete.append(self.downloaded_file_path)

        files_to_delete = [f for f in set(files_to_delete) if os.path.exists(f)]
        if not files_to_delete:
            messagebox.showinfo("提示", "当前没有发现可以清理的文件。")
            return

        confirm = messagebox.askyesno("⚠️ 确认删除", "确定要彻底删除相关的音视频文件吗？")
        if not confirm:
            return

        deleted_count = 0
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                self.update_ui_text(f"\n❌ 删除文件失败: {file_path}\n")

        if deleted_count > 0:
            self.update_ui_text(f"\n🗑️ 成功清理了 {deleted_count} 个本地文件！\n")
            self.file_path_var.set("将音频文件拖拽到此虚线框内，或点击右侧按钮选择 👇")
            self.downloaded_file_path = None

    def download_audio_from_url(self, url):
        self.update_ui_text("🌐 正在连接 B 站解析视频，并下载最高音质音频...\n")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                list_of_files = glob.glob('*.mp3')
                if list_of_files:
                    latest_file = max(list_of_files, key=os.path.getctime)
                    self.downloaded_file_path = os.path.abspath(latest_file)
                    self.update_ui_text(f"✅ 音频下载成功: {latest_file}\n")
                    return self.downloaded_file_path
                else:
                    raise Exception("下载成功，但找不到文件。")
        except Exception as e:
            self.update_ui_text(f"\n❌ 下载失败: {str(e)}\n")
            return None

    def convert_m4s_to_mp3(self, input_path):
        output_path = input_path.rsplit('.', 1)[0] + ".mp3"
        self.update_ui_text("⏳ 正在将本地 .m4s 转换为 .mp3 格式...\n")
        try:
            command = ['ffmpeg', '-y', '-i', input_path, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', output_path]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_path
        except Exception as e:
            messagebox.showerror("错误", f"转换失败，请检查 ffmpeg 环境。")
            return None

    def process_audio_thread(self):
        if not self.api_key:
            self.root.after(0, self.prompt_api_key)
            self.reset_button()
            return

        url_input = self.url_entry.get().strip()
        local_file = self.file_path_var.get()
        process_file = None

        try:
            if url_input.startswith("http"):
                process_file = self.download_audio_from_url(url_input)
                if not process_file:
                    self.reset_button()
                    return
            elif not "拖拽到此" in local_file and local_file:
                process_file = local_file
                if local_file.endswith('.m4s'):
                    process_file = self.convert_m4s_to_mp3(local_file)
                    if not process_file:
                        self.reset_button()
                        return
            else:
                messagebox.showwarning("提示", "请提供视频链接或音频文件。")
                self.reset_button()
                return

            client = genai.Client(api_key=self.api_key)

            import uuid
            original_dir = os.path.dirname(os.path.abspath(process_file))
            # 1. 创建唯一的临时文件名（用于上传），确保不与原文件冲突
            safe_filename = os.path.join(original_dir, f"temp_gemini_{uuid.uuid4().hex}.mp3")

            self.update_ui_text("⏳ 正在为云端上传准备临时文件...\n")

            # 🛠️ 核心修复（1）：复制用户文件，不再直接重命名原文件！
            # 使用 copy2 可以尽量保留文件的元数据
            shutil.copy2(process_file, safe_filename)

            try:
                # 在这个主要的 try...finally 块内处理本地副本的创建和上传后的清理
                self.update_ui_text("☁️ 正在上传音频至 AI 云端...\n")
                audio_file = client.files.upload(file=safe_filename)
                self.update_ui_text("🧠 上传成功！")

                # --- 嵌套：使用前一个针对云端文件清理的 try...finally ---
                try:
                    self.update_ui_text("🧠 Gemini 正在分析总结，请稍候...\n")

                    prompt = """
                                请你仔细聆听这段音频，这是一个视频的配音。
                                为了帮我节约时间，请你提供一个简短的、结构化的视频概要。
                                请包含以下内容：
                                1. 一句话总结视频核心主题。
                                2. 按逻辑列出 3-5 个核心要点或干货（用 bullet points）。
                                3. 过滤掉废话和片头片尾的寒暄.
                                """

                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=[prompt, audio_file]
                    )

                    self.update_ui_text(f"\n{'=' * 40}\n\n")
                    self.render_markdown(response.text)
                    self.update_ui_text(f"\n{'=' * 40}\n🎉 总结完毕！\n")

                finally:
                    # 🧹 针对云端文件的清理（整合上一个修复）
                    # 无论 generate_content 成功还是报错，强制清理云端临时文件
                    try:
                        client.files.delete(name=audio_file.name)
                        print(f"已清理云端临时文件: {audio_file.name}")  # 后台日志
                    except Exception as delete_err:
                        print(f"清理云端文件失败: {delete_err}")

            finally:
                # 🧹 核心修复（2）：无论上传成功、总结成功还是报错，强制删除本地临时 copy 文件！
                # 这样用户的原始文件（process_file）始终没有被修改或移动过，彻底根除“重命名失败”的风险。
                if os.path.exists(safe_filename):
                    os.remove(safe_filename)
                    print(f"已清理本地临时 copy 文件: {safe_filename}")

            # 👆 修改结束 👆

        except Exception as e:
            error_msg = str(e)
            if "API key not valid" in error_msg:
                self.update_ui_text(f"\n❌ API Key 无效，请点击右上角重新配置。\n")
            else:
                self.update_ui_text(f"\n❌ 发生错误: {error_msg}\n")
        finally:
            self.reset_button()

    def update_ui_text(self, text):
        self.root.after(0, lambda: self.result_text.insert(ctk.END, text))
        self.root.after(0, lambda: self.result_text.see(ctk.END))

    def render_markdown(self, text):
        def _insert_rendered():
            lines = text.split('\n')
            for line in lines:
                if line.startswith('### '):
                    self.result_text.insert(ctk.END, line[4:] + '\n', "h2")
                elif line.startswith('## '):
                    self.result_text.insert(ctk.END, line[3:] + '\n', "h2")
                elif line.startswith('# '):
                    self.result_text.insert(ctk.END, line[2:] + '\n', "h1")
                elif line.strip().startswith('* '):
                    line_content = line.replace('* ', '• ', 1)
                    self._parse_inline_bold(line_content)
                    self.result_text.insert(ctk.END, '\n')
                else:
                    self._parse_inline_bold(line)
                    self.result_text.insert(ctk.END, '\n')
            self.result_text.see(ctk.END)

        self.root.after(0, _insert_rendered)

    def _parse_inline_bold(self, text):
        # 补全了之前代码中丢失的正则表达式匹配标记
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                self.result_text.insert(ctk.END, part[2:-2], "bold")
            else:
                self.result_text.insert(ctk.END, part)

    def start_processing(self):
        self.result_text.delete(1.0, ctk.END)
        self.process_btn.configure(state="disabled", text="⏳ 处理中...")
        self.delete_btn.configure(state="disabled")
        threading.Thread(target=self.process_audio_thread, daemon=True).start()

    def reset_button(self):
        self.root.after(0, lambda: self.process_btn.configure(state="normal", text="🚀 开始提取核心摘要"))
        self.root.after(0, lambda: self.delete_btn.configure(state="normal"))


if __name__ == "__main__":
    root = TkinterDnD_CTk()
    app = VideoSummarizerApp(root)
    root.mainloop()
