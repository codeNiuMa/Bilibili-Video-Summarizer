# 验证记录

验证日期：2026-09-07。当前项目位于 `D:\code\mycode\python\first\Bilibili-Video-Summarizer`，使用现有 Conda `py311` 环境，并已同步 GitHub `main`。

## 已验证

- Windows，Python 3.11 Conda 环境。
- 远程 B 站链接恢复旧版单次 `extract_info(..., download=True)` 流程，不预查在线字幕。
- 自动化测试覆盖 FFmpeg 分段、单次下载、HTTP 412 提示、Google SDK 请求、重试、缓存、取消、长文字分块和 Qt 界面。
- `pip check` 通过。
- 主入口 `main.py --smoke-test` 使用当前 Conda Qt 环境启动 / 退出成功。
- 1240 × 900 默认窗口、1000 × 740 小窗口和设置对话框已渲染检查；离屏测试显式载入了本机中文字体，以弥补 offscreen 插件不枚举系统字体的问题。
- 所有 API 自动化测试均使用假响应，不产生付费调用。

## 实际联网检查的边界

此前的字幕预解析联网检查收到 B 站 HTTP 412。当前实现已删除该预解析请求，并恢复旧版单次音频下载；为避免在风控窗口内继续增加请求，本轮没有再次请求真实 B 站素材。

真实 B 站下载和 Gemini 端到端结果仍以用户网络、视频权限和 API 额度为准。

跨平台入口和 Windows CI 的 Python 3.11/3.12/3.13 配置已提供。

## 本机立即体验

在 `py311` 环境进入项目目录后执行 `python main.py`。
