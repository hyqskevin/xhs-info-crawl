# 博主发现阶段失败隔离测试案例

## 自动化

1. 第一个博主返回普通页面解析错误，第二个博主返回带签名 URL 的笔记。
2. 验证第二个博主仍被调用，已发现笔记进入处理。
3. 验证任务完成为 `COMPLETED_WITH_ERRORS`，日志记录失败博主。
4. 验证 `AuthenticationRequired` 仍暂停整批，不被普通异常隔离吞掉。
5. 运行后端全量测试。

## 真实任务 #7

1. 沿用任务 #7 原参数重新抓取，确认范围为 `keywords=0 bloggers=5`。
2. 确认“从零发现宁波”命中数量大于 0，URL 来自带 `xsec_token` 的 user/profile 结果。
3. 某一博主页面解析失败时，后续博主和已收集笔记继续处理。
4. 确认 `downloaded_notes > 0`。
5. 检查本次运行日志不存在 `Missing url` 或“requires a full signed URL”。

验收记录不得保存完整签名 URL、Cookie 或 Token。
