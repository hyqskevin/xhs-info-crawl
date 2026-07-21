# 活动管理支持关键字搜索设计

> 状态：审核中。

## 1. 目标

活动管理（`ActivitiesView`）有城市、日期区间、审核状态三个过滤器，但**没有关键字搜索**。当数据库 push 几百上千条推文，用户找不到具体推文。

## 2. 设计

### 2.1 后端

`backend/app/api/v1/notes.py::list_notes` 增加 `keyword: str | None = None` 参数。

模糊匹配 `Note.title`，用 `Title.ilike(f"%{keyword}%")` 即可（PostgreSQL ILIKE；SQLite 上 `LIKE` 默认大小写不敏感）；选 `ilike` 是因为 Python 后端会切换 DB provider 时行为一致。

```python
from sqlalchemy import or_

if keyword:
    pattern = f"%{keyword.strip()}%"
    if not pattern.strip("%"):
        pass
    else:
        filters.append(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
```

匹配 `title + content`。`content` 用 `ilike` 也 OK（小数据量没性能问题；数据量大加 GIN 索引或全文检索另议）。

### 2.2 前端

`ActivitiesView.vue` 的 `filters` reactive 增加 `keyword: ''`，toolbar 加一个 `<ElInput>` 输入框（前置 Search 图标），绑 v-model 到 `filters.keyword`。`applyFilters()` 时 `queryParams()` 透传 `keyword`。`resetFilters` 也清空 keyword。

UI 布局：

```
[城市 select] [关键字输入框] [日期范围] [审核状态] [筛选按钮] [重置按钮] [批量通过] [批量删除]
```

## 3. 测试

### 3.1 后端

`tests/test_notes_api.py` 新增 `test_list_notes_supports_keyword_filter`：

- mock 3 条 notes: "上海周末艺术展"、"宁波咖啡店"、"宁波艺术展"
- `GET /notes?keyword=艺术展` 返回 2 条
- `GET /notes?keyword=咖啡` 返回 1 条
- `GET /notes?keyword=` （空）不传 keyword，行为同不传

### 3.2 前端

`ActivitiesView.spec.ts` 新增：

- `filters.keyword` 设置为 '咖啡'，`api.notes` 调用包含 `keyword: '咖啡'`
- 点击"重置"按钮，keyword 重置为空字符串

## 4. 验收

- [ ] 后端 301+ 个测试全绿；
- [ ] 前端 42+ 个测试全绿；
- [ ] Playwright 走查：登录 → 活动管理 → 输入 "咖啡" → 列表只剩含"咖啡"的推文。
