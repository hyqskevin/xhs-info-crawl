# 博主白名单批量导入设计

> 状态：已通过持续授权审核并实现。

## 1. 目标

配置中心的“博主白名单”支持下载 Excel 模板并批量上传 `.xlsx` 或 UTF-8 `.csv`。导入时只使用用户可见的城市名称，不要求填写内部城市代码；重复上传同一文件必须幂等，不产生重复博主或重复城市绑定。

## 2. 方案选择

- 仅 CSV：依赖最少，但中文编码、分隔符和多城市填写体验较差；不采用。
- 仅 Excel：运营体验好，但不便脚本或纯文本生成；不采用。
- Excel + CSV，共用一套解析与校验（采用）：Excel 作为默认模板，CSV 作为兼容入口，导入后的业务语义完全一致。

## 3. 文件格式

模板列固定为：

| 列 | 必填 | 规则 |
|---|---:|---|
| 博主名称 | 是 | 去除首尾空格后 1–128 字符 |
| 小红书用户ID | 否 | 空值保留；非空时用于优先匹配 |
| 主页地址 | 否 | 空值保留；非空时用于次级匹配 |
| 关联城市 | 是 | 填配置中心城市名称；多城市用 `、`、中文/英文逗号或分号分隔 |
| 启用 | 否 | 空值默认“是”；支持“是/否、true/false、1/0” |

文件最多 500 条有效数据行，空行忽略。模板附一条示例，但下载模板本身不写数据库。

## 4. 后端边界

新增独立服务 `backend/app/services/blogger_import.py`：

- `parse_blogger_import(content, filename) -> list[BloggerImportRow]`：解析 xlsx/csv、规范字段并保留原始行号；
- `validate_blogger_import(rows, cities, existing_bloggers) -> ImportPlan`：校验列、城市、布尔值、文件内重复与歧义匹配；
- `apply_blogger_import(db, plan) -> ImportResult`：单事务执行新增/更新和城市绑定全量替换。

新增接口：

- `GET /api/v1/settings/bloggers/import-template`：下载 `.xlsx` 模板；
- `POST /api/v1/settings/bloggers/import?filename=<name>`：请求体直接发送文件字节，避免新增 multipart 运行依赖；仅接受 `.xlsx`/`.csv`，限制 2 MiB。

返回 `created`、`updated`、`total`。任一行出错返回 422，包含行号和原因，整批不落库。

## 5. 幂等与冲突规则

每行按以下优先级寻找既有博主：

1. 非空 `platform_user_id` 精确匹配；
2. 非空 `profile_url` 去除首尾空格后精确匹配；
3. `username` 去除首尾空格后精确匹配。

若三个条件命中不同记录，判定为歧义冲突并拒绝整批。匹配到同一记录则更新名称、非空 ID/主页、启用状态，并用本行城市全量替换绑定；没有命中则新增。文件内多行若指向同一记录或使用相同身份键，拒绝导入，避免后行静默覆盖前行。

## 6. 前端

仅在“博主白名单”tab 展示：

- “下载模板”：调用后端并下载 xlsx；
- “批量导入”：使用 Element Plus `ElUpload`/按钮及 `UploadFilled` 图标，限制单文件 `.xlsx,.csv`；
- 上传期间按钮 loading；成功 Toast 展示新增/更新数量并刷新列表；422 Toast 展示首个行号错误。

不使用 emoji，不显示城市代码，不自行实现文件选择控件。

## 7. TDD 与验收

1. 解析 xlsx/csv、多城市分隔和启用值；
2. 未知城市、缺名称、错误后缀、超限、重复身份和歧义匹配整批失败且数据库无变化；
3. 首次导入新增，重复导入更新且数量不增加，城市绑定正确替换；
4. 前端仅在博主 tab 显示模板和批量导入，上传成功刷新，失败显示行号；
5. 补充 Playwright 流程与测试案例文档；后端、前端、E2E 全量通过。

## 8. 不在本次范围

- 不在导入时自动调用 OpenCLI 补全主页；缺主页的记录仍可导入并沿用现有“补充博主信息”；
- 不支持 `.xls`、JSON 或压缩包；
- 不新增数据库表或环境变量。

## 9. 验收结果

- 后端导入与配置回归 `28 passed`，覆盖 xlsx/csv、模板、幂等更新、原子回滚、行号错误、2 MiB 限制与鉴权。
- 全量后端 `227 passed, 1 skipped`；前端组件 `31 passed`，其中 SettingsView `8 passed`；生产构建成功。
- Playwright `39 passed`，新增案例验证模板下载、CSV 文件上传、成功 Toast 和导入后列表刷新。
- `git diff --check` 通过；实现没有新增数据库迁移、依赖或环境变量。
