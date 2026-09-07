# 验证记录

验证日期：2026-09-07。基于原仓库提交 `7a14dc6`，本地分支 `refactor/desktop-v2`。用户提供的 Downloads/main.py 与仓库 main.py 的 SHA-256 一致。

## 已验证

- Windows，Python 3.12.14。
- 37 项自动化测试通过。包含真实 FFmpeg 音频分段和中文路径保护、真实 yt-dlp 字幕写入、字幕提取开关与失败回退、HTTP 412 提示、实际 Google SDK 经 MockTransport 的请求序列化和 429 重试、云端文件清理与取消、结果缓存、长文字分块、Qt 历史查看与复制。
- `ruff check .` 通过；代码已按 Ruff 格式化。
- `pip check` 通过。
- 主入口 `main.py --smoke-test` 在 Qt offscreen 模式启动 / 退出成功。
- 1240 × 900 默认窗口、1000 × 740 小窗口和设置对话框已渲染检查；离屏测试显式载入了本机中文字体，以弥补 offscreen 插件不枚举系统字体的问题。
- 所有 API 自动化测试均使用假响应，不产生付费调用。

## 实际联网检查的边界

尝试使用 yt-dlp 自带测试素材链接 `https://www.bilibili.com/video/BV13x41117TL` 读取视频信息，当前网络收到 B 站 HTTP 412 风控响应，没有完成音频下载。应用已为该响应提供明确提示，不对风控继续反复重试。未使用个人 Cookie，也没有绕过访问限制。

没有用户提供的 Gemini API Key，未执行真实 Gemini 音频上传和总结。因此，**不能将本轮结果理解为真实 B 站 + Gemini 端到端已通过**；需要在可访问 B 站的网络、有效 API 项目和必要时有效 Cookie 下完成一次真实素材验收。具体模型额度、内容质量和地区可用性以实际调用为准。

跨平台入口和 Windows CI 的 Python 3.11/3.12/3.13 配置已提供，但本地仅实际执行了 Windows Python 3.12 测试，未运行 GitHub Actions。

## 本机立即体验

在本项目外一层 `outputs/` 中双击 `启动 Bili Notes.cmd`，会使用本次已安装好的隔离环境启动。此快捷入口依赖当前任务的 `work/venv`，移动源码到其他位置或其他电脑时，请按 README 安装并使用项目内的 `启动.bat`。

本次仅修改本地工作副本，保留原始文件与原仓库许可证，没有推送远端仓库。
