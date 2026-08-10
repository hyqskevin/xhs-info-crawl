# 废弃 legacy 关键词表 + 修复关键词组管理 bug

## 1. 背景

用户 2026-08-10 反馈：
- 关键词组与城市抓取配置重复（legacy `keywords` 表 vs `keyword_groups`）
- 关键词组名称无法修改
- 关键词输入后不展示在输入框里
- 仪表盘抓取流程已符合需求（城市必选 + 活动组/博主选填 + 都选时混合抓取），无需改动

## 2. 需求

### 2.1 废弃 legacy `keywords` 表（方案 A）
- 删除 `keywords` 模型、`_resolve_from_legacy_keyword_table`、crawl_scope 中的 legacy 兜底分支
- 配置中心「城市」tab 移除关键词管理（只保留城市基础信息）
- 写 alembic migration `drop_table('keywords')`
- DB 数据已重复（关键词组表已存完整数据），直接删 legacy 表

### 2.2 修复关键词组管理 bug
- **bug1 名称无法修改**：
  - 后端新增 `PATCH /keyword-groups/{id}` 端点，更新 name/description/enabled
  - name 唯一约束，重名报 409（与 create 一致）
  - 前端解除 `:disabled="!!editingId"` 限制
  - 前端 `save()` 编辑分支调用 PATCH 端点更新名称
- **bug2 关键词输入后不展示**：
  - 根因：`:model-value="''"` 受控模式 + `e.target.value = ''` 手动清空，Vue 响应式未正确触发
  - 修复：改用临时变量 `newWord` 绑定 ElInput，回车后 push 到 `form.words` 并清空 `newWord`
  - 保持当前交互（回车添加 + ElTag 展示可删除）

### 2.3 仪表盘抓取流程（无需改动）
当前 DashboardView 已实现：
- 城市必选（[第 161 行](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/DashboardView.vue#L161)）
- 关键词组选填，按当前城市过滤（[第 94 行](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/DashboardView.vue#L94)）
- 博主选填
- 都选时混合抓取（type: 'mixed'，[第 169 行](file:///Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl/frontend/src/views/DashboardView.vue#L169)）

## 3. 设计

### 3.1 后端改动

**新增 PATCH 端点**（`backend/app/api/v1/settings.py`）：
```python
class KeywordGroupUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None

@router.patch("/keyword-groups/{kg_id}")
def patch_keyword_group(kg_id: int, payload: KeywordGroupUpdateIn, _: Admin, db: DB) -> dict:
    kg = db.get(KeywordGroup, kg_id)
    if kg is None: raise HTTPException(404, "关键词组不存在")
    if payload.name is not None and payload.name != kg.name:
        existing = db.scalar(select(KeywordGroup).where(KeywordGroup.name == payload.name))
        if existing: raise HTTPException(409, "关键词组名称已存在")
        kg.name = payload.name
    if payload.description is not None: kg.description = payload.description
    if payload.enabled is not None: kg.enabled = payload.enabled
    db.commit()
    return {"code": 200, "message": "success", "data": _dump_keyword_group(db, kg)}
```

**删除 legacy 关键词**：
- `backend/app/models/config.py`：删除 `Keyword` 类
- `backend/app/services/crawl_scope.py`：删除 `_resolve_from_legacy_keyword_table` 和 `resolve_effective_keywords` 中的 legacy 兜底分支
- `backend/app/api/v1/settings.py`：删除 keywords 相关 CRUD 端点（如有）
- `backend/app/api/v1/cities.py` 或对应文件：删除城市详情中的 keywords 关联
- 新增 alembic migration `0020_drop_keywords_table.py`

### 3.2 前端改动

**KeywordGroupSettings.vue**：
- 解除名称输入框 `:disabled` 限制
- `save()` 编辑分支新增 `api.patchKeywordGroup(id, {name, description, enabled})` 调用
- 关键词输入改用临时变量：
  ```vue
  <ElInput v-model="newWord" placeholder="回车添加" @keyup.enter="addWordFromInput" />
  ```
  ```ts
  const newWord = ref('')
  function addWordFromInput() {
    if (addWord(newWord.value)) newWord.value = ''
  }
  ```

**SettingsView.vue「城市」tab**：
- 移除关键词管理相关代码（如有）

**api/client.ts**：
- 新增 `patchKeywordGroup(id, payload)` 方法

## 4. 验收

- [ ] 后端新增 `PATCH /keyword-groups/{id}` 端点，支持更新 name/description/enabled
- [ ] name 重名时返回 409
- [ ] 删除 `keywords` 表（migration drop_table）
- [ ] 删除 `Keyword` 模型、`_resolve_from_legacy_keyword_table`、legacy 兜底分支
- [ ] 前端关键词组名称可编辑
- [ ] 前端关键词输入后正确展示为 ElTag
- [ ] 编辑关键词组时名称/说明/关键词/城市都能正常更新
- [ ] 仪表盘抓取流程不受影响（城市必选 + 活动组/博主选填 + 混合抓取）
- [ ] 后端全量测试通过，无回归
- [ ] 前端全量测试通过，build 通过

## 5. 部署

- migration 需执行 `alembic upgrade head`
- **worker 必须重启**（改动 `app/services/crawl_scope.py`）
- uvicorn `--reload` 自动加载 API 层
- 前端 dev server 自动刷新
