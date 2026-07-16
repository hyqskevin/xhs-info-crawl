# 外部依赖实测记录

日期：2026-07-16

## OpenCLI + 小红书

- OpenCLI：v1.8.6
- Daemon：通过
- Chrome 扩展：v1.0.22，已连接
- Connectivity：通过
- `xiaohongshu whoami`：登录成功
- Cookie：由 OpenCLI 扩展从当前 Chrome 会话中复用；项目未读取、打印或持久化 Cookie 明文
- 2026-07-16 最终复测：登录检查通过，只读搜索“上海 周末活动”返回 3 条近一周笔记。
- 复测期间发现旧 daemon 占用 19825 但无响应；重启 daemon 后恢复。测试脚本现已区分错误码 69（浏览器连接）和 77（需要登录）。
- 只读搜索：`上海 周末活动`，限制 3 条，成功返回结果

复测命令：

```bash
make test-opencli
```

该脚本先执行 `doctor` 和 `whoami`。登录失败时以 77 退出，禁止继续搜索。

## MiniMax

- 官方国内基础地址：`https://api.minimaxi.com/v1`
- 接口：`/text/chatcompletion_v2`
- 模型：`MiniMax-M3`
- 实测：HTTP 200，存在 `choices`、`usage`，`base_resp.status_code = 0`
- `/v1/models` 实测包含 `MiniMax-M3`，且最小 M3 文本请求成功返回模型名 `MiniMax-M3`
- API Key：仅保存于被 Git 忽略的 `.env`，本记录不包含 Key

由于 API Key 曾通过聊天传递，建议验证结束后在 MiniMax 控制台轮换密钥，并更新本地 `.env`。

## PaddleOCR

- Python：3.11.15（macOS arm64）
- 已安装可选依赖：`paddleocr 3.7.0`、`paddlepaddle 3.3.1`
- 业务适配器为 Celery Worker 内惰性单例；首次导入/首次模型下载可能较慢。
- 确定性自动化测试使用假 OCR 引擎，不依赖网络下载模型；真实图片验收需将 `OCR_ENABLED=true` 并在首次运行时保持网络可用。
- 真实全链路任务 2：下载 16 张图片，PaddleOCR 16/16 成功，OCR 总文本 5683 字符。

## 多活动抽取与日期归档

- 真实笔记：1 篇上海周末活动合集。
- MiniMax-M3：通过 Function Calling 从标题、正文和 16 张图片 OCR 文本中拆出 14 个具体活动。
- SQLite：14 条 `activities`，均关联同一 `note_id`、保留原文 `source_url`，并包含 `source_image_indexes`。
- 归档：`data/archive/2026-07-16/task-2/`，包含 16 张图片、`source.md`、`activities.md` 和 `activities.xlsx`。
- Excel 数据行：14；Markdown 活动小节：14。
