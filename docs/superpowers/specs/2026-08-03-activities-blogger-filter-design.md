# 活动管理增加按博主筛选推文

**日期**: 2026-08-03
**状态**: 已审核

## 目标

活动管理（推文列表）页增加"博主"筛选下拉框，选择博主后只显示该博主发布的推文。

## 设计

### 后端

`GET /notes` 新增 `blogger_id` 查询参数（可选）。当传入时：
1. 查询博主 `profile_url`
2. 过滤 `Note.source_url LIKE profile_url%`（匹配以博主主页 URL 开头的推文链接）

### 前端

`ActivitiesView.vue` 工具栏新增"博主"下拉框（ElSelect）：
- 来源：调用 `api.settings('bloggers')` 获取博主列表
- 按当前城市过滤（`blogger.city_codes` 包含当前城市）
- 支持搜索（filterable）
- 选择博主后列表刷新，清空博主恢复全部

## 验收

- 后端 `GET /notes?blogger_id=1` 返回该博主推文
- 前端博主下拉按城市过滤，选择后列表刷新
- 清空博主下拉恢复全部推文
- 后端全量测试通过，前端 build 通过