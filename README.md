# B站视频总结工具 · Simple v3

这是一次从零重写的版本，目标不是功能堆叠，而是：**流程简单、代码能看懂、出错能排查**。


## 保留下载音频

默认情况下，B 站下载的原始音频只存放在系统临时目录中，并在总结任务结束后自动清理。

如果希望保留原始音频，在界面顶部开启 **“保留下载音频”** 开关。开启后，每次通过 B 站链接下载得到的原始音频会额外复制到：

```text
项目目录/downloads/
```

文件名使用“视频标题 + BV号”，例如：

```text
某个视频标题 [BVxxxxxxxxxx].m4a
```

界面的 **“打开目录”** 按钮可以直接打开该文件夹。关闭开关后仍保持原先的自动清理行为。

> 该开关只影响 B 站网络下载的原始音频；本地拖入的文件不会被复制。Gemini 使用的 16 kHz 单声道临时 MP3 仍会在任务结束后清理。

## 流程

```text
B站链接 ── yt-dlp 单次解析下载 ─┐
                                ├─ FFmpeg 转 16 kHz 单声道 MP3 ─ Gemini ─ Markdown 总结
本地音视频 ─────────────────────┘
```

没有字幕预解析、没有手写 Bilibili API、没有 WBI 自己签名、没有缓存层，也不会为了 412 在后台连续请求很多次。

## 文件

```text
main.py                 启动入口
app.py                  CustomTkinter 图形界面
downloader.py           yt-dlp 下载 + FFmpeg 音频转换
gemini_summarizer.py    Gemini Files API + 总结
settings.py             本地设置/API Key
requirements.txt        依赖
启动.bat                Windows 双击启动
```

## 环境

推荐 Python 3.11 或更新版本。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
python main.py
```

Windows 也可以安装完成后直接双击 `启动.bat`。

FFmpeg：优先使用系统 PATH 中的 `ffmpeg`；如果没有，则自动使用 `imageio-ffmpeg` 自带的 ffmpeg，一般无需额外配置。

## Gemini

默认模型：

```text
gemini-3.5-flash-lite
```

它是稳定的低成本多模态模型，支持音频输入。界面中也可以切换其他 Gemini 模型。

第一次启动点击右上角 `API Key`。Key 保存在：

```text
~/.bili_summarizer/api_key.txt
```

也可以不保存文件，直接设置环境变量：

```text
GEMINI_API_KEY
```

环境变量优先级更高。

## B站 412

2026 年仍存在 yt-dlp 访问 Bilibili 时被返回 `412 / request was banned` 的情况。这不是 Gemini 阶段的错误。

这个版本做三件事：

1. 只进行一次 `extract_info(..., download=True)`，不先查字幕再重新解析。
2. 保留完整 yt-dlp 日志到：

```text
~/.bili_summarizer/logs/latest_yt_dlp.log
```

3. 支持可选 Cookie 文件。对于需要登录权限、会员权限或账号可见的视频，可以在右上角 `Cookie` 选择你自己账号导出的 Netscape 格式 cookies.txt。

如果普通公开视频也遇到 412：

```bash
python -m pip install -U yt-dlp
```

然后重新测试。仍然失败时不要让程序高速重复请求，稍后重试，或使用 B 站客户端/浏览器已取得的本地音视频文件。

> 注意：下载日志可能含视频请求 URL 等信息。公开贴日志前请检查其中是否有你不想暴露的参数。

## 为什么不再分段上传

当前 Gemini Files API 支持较大的媒体文件。这个版本先把音频压成 `16 kHz / mono / 64 kbps MP3`，然后一次上传、一次总结。这样代码和结果都更容易理解。

如果以后实际遇到超长视频或 API 单文件限制，再单独增加“超长音频分段”，而不是一开始就把整个项目复杂化。
