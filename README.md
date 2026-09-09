# Bilibili Video Summarizer

一个面向 Bilibili 视频的桌面 AI 总结工具。

项目使用 **PySide6** 构建现代化桌面界面，通过 **yt-dlp** 获取 B 站视频音频，使用 **FFmpeg** 将音频转换为适合上传的语音文件，再交给 **Google Gemini** 生成结构化 Markdown 视频笔记。

当前版本重点保持一个原则：

> **UI 可以持续迭代，但已经验证稳定的下载、音频处理和 Gemini 总结流程尽量不动。**

---

## ✨ 功能

- 🔗 粘贴 Bilibili 视频链接直接总结
- 📁 支持拖入或选择本地音视频文件
- 🎧 使用 yt-dlp 下载 B 站最高可用音质
- 🛠️ 使用 FFmpeg 自动转换为适合 Gemini 的音频
- 🧠 使用 Gemini 对完整音频进行理解和总结
- 📑 Markdown 结果可视化渲染
- 📋 一键复制原始 Markdown
- 💾 保存 Markdown 笔记
- 🔄 根据当前 API Key 动态刷新可用 Gemini 模型
- 🍪 支持 Netscape 格式 Cookie 文件
- 📥 可选择保留 B 站下载的原始音频
- 📜 保留完整 yt-dlp 下载日志，方便排查 412 等问题
- 🌙 深色 / 浅色主题
- 🪟 PySide6 无边框一体化桌面窗口

---

## 🖥️ 当前界面

当前桌面界面采用 PySide6 实现，主要由以下区域组成：

- 左侧连接状态与模型设置
- B 站链接 / 本地文件输入区
- 任务进度与运行状态
- Markdown 总结结果区域
- API Key、Cookie、下载日志等设置入口

窗口使用自定义无边框界面和矢量图标，目标是在保留 Windows 桌面应用操作习惯的同时，提供更现代、统一的视觉体验。

---

## 🔄 工作流程

```text
Bilibili 链接
    │
    ▼
yt-dlp 单次解析并下载音频
    │
    ├───────────────┐
    │               │ 可选
    │               ▼
    │          保留原始音频
    │          downloads/
    │
    ▼
FFmpeg
16 kHz / Mono / 64 kbps MP3
    │
    ▼
Gemini Files API
    │
    ▼
Gemini 多模态音频理解
    │
    ▼
结构化 Markdown 视频笔记
```

本地音视频文件会跳过 yt-dlp 下载阶段，直接进入 FFmpeg 和 Gemini 流程。

---

## 🧩 项目设计

项目目前刻意保持较简单的模块划分：

```text
Bilibili-Video-Summarizer/
│
├─ main.py
├─ app.py
├─ downloader.py
├─ gemini_summarizer.py
├─ settings.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ 启动.bat
└─ downloads/              # 可选保留的原始音频，默认不提交 Git
```

### 文件职责

| 文件 | 作用 |
| --- | --- |
| `main.py` | 程序启动入口 |
| `app.py` | PySide6 图形界面、窗口交互、任务线程 |
| `downloader.py` | yt-dlp 下载与 FFmpeg 音频处理 |
| `gemini_summarizer.py` | Gemini 模型列表、Files API、音频总结 |
| `settings.py` | API Key、模型、主题、Cookie、下载目录等本地配置 |
| `requirements.txt` | Python 运行依赖 |
| `启动.bat` | Windows 快捷启动 |

核心后台逻辑和 UI 分离，后续 UI 更新尽量只修改 `app.py`。

---

## 🚀 安装

推荐：

- Windows 10 / 11
- Python 3.11+
- 可访问 Gemini API 的网络环境

### 1. 克隆仓库

```bash
git clone https://github.com/codeNiuMa/Bilibili-Video-Summarizer.git
cd Bilibili-Video-Summarizer
```

### 2. 创建虚拟环境

使用 Conda：

```bash
conda create -n bili python=3.11 -y
conda activate bili
```

或者使用 Python venv：

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. 安装依赖

```bash
python -m pip install -U pip
pip install -r requirements.txt
```

### 4. 启动

```bash
python main.py
```

Windows 也可以使用：

```text
启动.bat
```

---

## 📦 Python 依赖

当前 PySide6 版本至少需要：

```text
PySide6
google-genai
yt-dlp
imageio-ffmpeg
certifi
```

FFmpeg 优先使用系统 `PATH` 中的 `ffmpeg`。

如果系统没有安装 FFmpeg，程序会尝试使用 `imageio-ffmpeg` 提供的可执行文件。

---

## 🔑 Gemini API Key

首次运行后，在左侧设置区域点击：

```text
API Key
```

输入自己的 Gemini API Key。

默认保存在：

```text
~/.bili_summarizer/api_key.txt
```

Windows 通常对应：

```text
C:\Users\<用户名>\.bili_summarizer\api_key.txt
```

也可以使用环境变量：

```text
GEMINI_API_KEY
```

如果环境变量存在，会优先使用环境变量。

> API Key 不应提交到 GitHub。

---

## 🤖 动态刷新 Gemini 模型

软件支持根据当前 API Key 请求 Gemini Models API，并筛选支持：

```text
generateContent
```

的 Gemini 模型。

因此不需要长期在代码中手动维护固定模型列表。

界面中的刷新按钮可以重新获取当前 API Key 实际可用的模型，并在下拉框中选择。

当前默认模型：

```text
gemini-3.5-flash-lite
```

实际可用模型以当前 Gemini API 返回结果为准。

---

## 🍪 Bilibili Cookie

普通公开视频通常可以直接下载。

如果遇到：

- 登录后可见视频
- 会员内容
- 账号权限内容
- 某些受限制的视频

可以在设置中选择自己的 Netscape 格式：

```text
cookies.txt
```

为了避免修改用户原始 Cookie 文件，程序会在临时目录中复制一份后交给 yt-dlp 使用。

---

## 📥 保留下载音频

默认情况下，B 站下载得到的原始音频只存在于任务临时目录。

总结完成后会自动清理。

如果开启：

```text
保留下载音频
```

程序会额外保存一份原始音频到：

```text
项目目录/downloads/
```

文件名类似：

```text
视频标题 [BVxxxxxxxxxx].m4a
```

如果同名文件已经存在，会自动添加序号，不覆盖旧文件。

本地拖入的音视频文件不会被复制。

Gemini 使用的临时 MP3 仍然会在任务结束后清理。

---

## 🛠️ 音频处理

为了减少 Gemini 上传文件体积，程序会将输入媒体转换为：

```text
16 kHz
Mono
MP3
64 kbps
```

转换后的临时文件名为：

```text
audio_for_gemini.mp3
```

其作用只是作为 Gemini 输入，不作为永久媒体文件保存。

---

## 📝 Gemini 总结内容

当前提示词要求 Gemini 输出高质量中文 Markdown 视频笔记，主要包含：

- 一句话总结
- 核心内容
- 重要概念、论据、数据或例子
- 值得记住的结论
- 教程类视频可选的操作步骤

同时过滤：

- 片头片尾
- 重复口头禅
- 点赞关注提醒
- 无意义寒暄
- 广告式废话

界面会渲染 Markdown 以提高阅读体验。

“复制 Markdown”和“保存 Markdown”仍然保留原始 Markdown 内容。

---

## 📜 下载日志

每次 yt-dlp 运行都会保留详细日志：

```text
~/.bili_summarizer/logs/latest_yt_dlp.log
```

遇到下载问题时，可以优先查看：

```text
下载日志
```

日志可以帮助判断问题发生在：

```text
Bilibili 网页解析
WBI
视频格式接口
媒体 CDN
代理
Cookie
```

中的哪一步。

> 日志中可能包含视频请求 URL 和参数。公开发布日志前请先检查敏感内容。

---

## ⚠️ Bilibili 412 / request was banned

Bilibili 可能根据访问环境、请求策略、账号状态、网络出口等因素返回：

```text
HTTP 412
request was banned
```

当前项目不会自己实现 Bilibili API 或 WBI 签名，而是尽量保持简单：

```python
yt_dlp.YoutubeDL(...).extract_info(url, download=True)
```

即：

> **一次 yt-dlp 解析 + 下载，不额外进行字幕预解析或重复请求。**

如果出现 412，可依次尝试：

1. 确认视频在浏览器中可以正常播放。
2. 更新 yt-dlp：

```bash
python -m pip install -U yt-dlp
```

3. 如果视频需要账号权限，配置自己的 Cookie。
4. 检查 VPN / 代理出口。
5. 稍后重试。
6. 使用已经下载的本地媒体文件进行总结。

412 发生在 Bilibili / yt-dlp 下载阶段，与 Gemini 总结阶段是两套独立流程。

---

## 🌐 代理说明

yt-dlp 默认会继承 Python / 系统环境中的代理设置。

例如：

```text
HTTP_PROXY
HTTPS_PROXY
```

如果日志中出现：

```text
Proxy map
```

说明 yt-dlp 已检测到代理。

是否真正消耗代理节点流量，还取决于代理软件自己的分流规则，例如：

```text
DIRECT
PROXY
```

---

## 💾 本地配置

程序本地数据默认保存在：

```text
~/.bili_summarizer/
```

主要包括：

```text
.bili_summarizer/
├─ api_key.txt
├─ config.json
└─ logs/
   └─ latest_yt_dlp.log
```

`config.json` 保存：

- 当前 Gemini 模型
- Cookie 文件路径
- 是否保留下载音频
- 界面主题

这些文件不属于项目源码，不应提交到 GitHub。

---

## 🛡️ 隐私说明

项目不会主动上传用户的 API Key、Cookie 或本地设置到 GitHub。

处理网络视频时：

- Bilibili 音频由 yt-dlp 下载到本机
- FFmpeg 在本地转换音频
- 转换后的音频上传至 Gemini Files API
- 总结结束后程序会尝试删除 Gemini 云端临时文件
- 本地任务临时目录结束后自动清理

使用 Gemini 即代表音频内容需要上传到 Google Gemini 服务处理。

---

## 🧪 维护原则

这个项目曾经经历过一次过度重构，因此当前版本明确遵循：

### 1. 稳定工作流优先

已经验证正常的：

```text
yt-dlp → FFmpeg → Gemini
```

除非确实存在功能问题，否则不轻易重构。

### 2. UI 与后台分离

视觉优化主要集中在：

```text
app.py
```

后台逻辑集中在：

```text
downloader.py
gemini_summarizer.py
settings.py
```

### 3. 小步提交

优先采用：

```text
修改
→ 本地测试
→ Git commit
→ 再继续修改
```

避免一次修改整个项目。

### 4. 正式版本使用 Git Tag + GitHub Release

例如：

```text
v0.1.0  首个稳定工作版本
v0.2.0  PySide6 现代 UI
v0.2.1  Bug 修复
v0.3.0  新功能
v1.0.0  正式稳定版本
```

---

## 📌 当前版本

### v0.2.0

主要变化：

- 使用 PySide6 重构桌面 UI
- 无边框一体化窗口
- 深色 / 浅色主题
- Markdown 可视化渲染
- Fluent 风格矢量图标
- 动态 Gemini 模型刷新
- 保留下载音频
- 状态胶囊与任务进度显示
- 优化窗口圆角、布局与交互细节

核心处理流程保持：

```text
yt-dlp → FFmpeg → Gemini
```

---

## 🗺️ 后续计划

可能的后续方向：

- Windows 可执行文件打包
- GitHub Release 自动构建
- 更完整的 Windows 11 窗口交互
- 视频标题和基本信息展示
- 更丰富的总结模板
- 超长音频分段策略
- 更完整的异常诊断
- 自动检查 yt-dlp 更新

---

## 🙏 说明

本项目主要用于个人学习、视频内容整理和技术实践。

请遵守 Bilibili、Google Gemini 以及所在地区的相关服务条款和法律法规。
