# 外部依赖实测记录

日期：2026-07-16

## OpenCLI + 小红书

- OpenCLI：v1.8.6
- Daemon：通过
- Chrome 扩展：v1.0.22，已连接
- Connectivity：通过
- `xiaohongshu whoami`：登录成功
- Cookie：由 OpenCLI 扩展从当前 Chrome 会话中复用；项目未读取、打印或持久化 Cookie 明文
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
