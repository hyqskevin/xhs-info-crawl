# 系统配置页 + 定时任务抓取批次

**日期**: 2026-08-03
**状态**: 已审核

## 背景

当前 `.env` 中的配置项（MiniMax、PaddleOCR、流水线重试、小红书滚动策略、抓取数量等）只能通过修改 `.env` 文件并重启服务生效，无法在界面上实时调整。用户希望将这些配置搬到配置中心，方便可视化管理。

## 目标

1. 配置中心新增"系统配置" tab，集中管理以下 env 级配置：
   - 活动识别模型（MiniMax）
   - PaddleOCR
   - 单笔记流水线重试
   - 小红书滚动策略
   - 抓取数量
2. 定时任务页面支持配置抓取批次参数

## 设计

### 后端

新增 `GET/PUT /api/v1/settings/system-config` 端点：

**GET** 返回当前所有可配置项的值（从 Settings 读取）。

**PUT** 接收部分字段更新，写入 `.env` 文件（保留其他字段不变），返回更新后的全量配置。

**配置项分组**：

| 分组 | 字段 | 类型 | 默认值 |
|---|---|---|---|
| 活动识别模型 | minimax_api_key | str(password) | "" |
| | minimax_base_url | str | https://api.minimaxi.com/v1 |
| | minimax_model | str | MiniMax-M3 |
| | minimax_timeout_seconds | int | 180 |
| PaddleOCR | ocr_enabled | bool | false |
| | ocr_language | str | ch |
| | ocr_min_confidence | float | 0.5 |
| 流水线重试 | pipeline_stage_max_retries | int | 2 |
| | pipeline_stage_retry_delay_seconds | float | 2 |
| 小红书滚动 | xhs_search_target_count | int | 50 |
| | xhs_search_scroll_max_rounds | int | 8 |
| | xhs_scroll_pixels | int | 800 |
| | xhs_scroll_stagnant_rounds | int | 2 |
| 抓取数量 | search_limit | int | 50 |
| | weekly_search_limit | int | 500 |
| | consecutive_note_failure_limit | int | 3 |
| | activity_future_window_days | int | 60 |

### 前端

**SettingsView.vue** 新增"系统配置" tab（RadioButton），展示分组表单，修改后点"保存"调 PUT 接口。

**SchedulesView.vue** 新增"抓取批次" tab，展示抓取数量相关配置（search_limit、weekly_search_limit、xhs_search_target_count 等），与系统配置页共享同一后端接口，但仅展示抓取相关字段。

### 持久化

写 `.env` 文件：读取现有 `.env`，按 key 更新对应行，不存在的 key 追加到文件末尾。保留注释和空行。更新后 Settings 实例需重新加载（或提示用户重启服务）。

> 注意：修改 `.env` 后，uvicorn `--reload` 会自动重载 API 进程；但 celery worker/beat 不会自动重载，**需要手动重启**才能让新配置在抓取流程中生效。

## 验收

- 配置中心新增"系统配置" tab，按分组展示所有可配置项
- 修改并保存后，`GET /settings/system-config` 返回更新后的值
- `.env` 文件正确更新，注释和空行保留
- 定时任务页新增"抓取批次" tab，展示抓取数量相关配置
- 后端全量测试通过，前端 build 通过