# ✨ B站长视频省流神器 (Bilibili Video Summarizer)

这是一个基于 Python 和 Google Gemini API 开发的现代化桌面小工具。它可以自动下载 B 站视频的音频，或读取本地音视频文件，利用大模型快速提取长视频的核心摘要和干货要点，帮你大幅节省观看“注水”视频的时间！

<img width="1252" height="1039" alt="image" src="https://github.com/user-attachments/assets/bfbfa358-27cf-4c74-8a45-9c238b7474f1" />

## 🌟 核心功能

- **🔗 一键网络解析：** 直接粘贴 B 站视频链接，后台自动调用 `yt-dlp` 抓取最高音质音频。
- **📁 丝滑拖拽支持：** 支持将本地 `.m4s`, `.mp3`, `.wav` 等格式文件直接拖拽进软件窗口进行处理。
- **🧠 智能提炼摘要：** 接入最新版 `google-genai` (Gemini 2.0 Flash 模型)，自动过滤废话，精准提炼 3-5 个核心干货。
- **🎨 现代化 UI：** 采用 `customtkinter` 构建，原生支持系统级暗黑模式，自带 Markdown 加粗排版渲染。
- **🔒 隐私与便利：** API Key 加密保存在用户本地底层目录，一次配置，永久生效。
- **🧹 强迫症福音：** 提供“一键删除本地文件”按钮，看完摘要随手清理缓存垃圾。

## 🛠️ 准备工作

在运行本项目之前，请确保你的电脑上已安装以下环境和工具：

1. **Python 3.8+**
2. **FFmpeg (必需)：** 本工具依赖 FFmpeg 进行音视频格式转码。
   - 请前往 [FFmpeg 官网](https://ffmpeg.org/download.html) 或 [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 下载 Windows 版 `ffmpeg.exe`。
   - **最简单的方法：** 将下载的 `ffmpeg.exe` 直接放入本项目的源代码同一级目录下。
3. **Gemini API Key：** 请前往 [Google AI Studio](https://aistudio.google.com/) 免费申请一个 API Key。

## 📦 安装指南

1. 克隆本仓库到本地：
   ```bash
   git clone [https://github.com/你的用户名/你的仓库名.git](https://github.com/你的用户名/你的仓库名.git)
   cd 你的仓库名
