# 城市去重（修复重复 city 行）一次性脚本设计

> 状态：审核中。

## 1. 目标

截图：仪表盘城市下拉出现 **"宁波 + 上海 + 宁波"**——DB 中真实存在两条 `City` 行都是「宁波」。

一次性脚本：选最新启用项为 canonical，把其它重复 name 的 City 的关联数据迁移过去，删多余。

## 2. 行为

1. 列出 `SELECT name, COUNT(*) FROM cities GROUP BY name HAVING COUNT(*) > 1`；
2. 对每个重复组：
   - 选 `id ASC` 最小、且 `enabled=True` 的为 canonical；若无启用项，取 `id ASC` 最小；
   - 把其它行（记为 `dup`）迁移：
     - `UPDATE notes SET city_code = canonical.code WHERE city_code = dup.code`；
     - `UPDATE blogger_city SET city_code = canonical.code WHERE city_code = dup.code`；
     - `UPDATE keyword_group_cities SET city_code = canonical.code WHERE city_code = dup.code`（即使 0013 还没跑也兼容：脚本仅做"已有的 city_code 列"替换；
     - `UPDATE crawl_tasks.params ...` 中 city 字段替换（读 JSON `params['city']`）；
   - 把 `keywords (city_code)`、`cities` 中其它 dup 行 `DELETE`；
3. 写日志 `INFO`：[before/after counts]。
4. 幂等：二次跑无变化。

## 3. 实现

`backend/scripts/dedupe_cities.py`：

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    stats = {"before": 0, "after": 0, "merged_groups": 0}
    stats["before"] = db.scalar(select(func.count()).select_from(City)) or 0
    dupes = db.execute(text("SELECT name FROM cities GROUP BY name HAVING COUNT(*) > 1"))
    for (name,) in dupes:
        rows = db.scalars(select(City).where(City.name == name).order_by(City.id)).all()
        canonical = next((c for c in rows if c.enabled), rows[0])
        for dup in rows:
            if dup.id == canonical.id: continue
            _migrate(db, "notes", canonical.code, dup.code)
            _migrate(db, "blogger_city", canonical.code, dup.code)
            _migrate(db, "crawl_tasks", canonical.code, dup.code)  # JSON
            db.delete(dup)
            stats["merged_groups"] += 1
    db.commit()
    stats["after"] = db.scalar(select(func.count()).select_from(City)) or 0
    print(stats)
```

## 4. 测试

`tests/test_dedupe_cities_script.py`：

| case | 步骤 | 期望 |
|---|---|---|
| test_dedupe_keeps_oldest_enabled_city | seed City(a: nbo, enabled), City(b: nb, enabled) | 保留 a，b 删除，notes.city_code 改 a |
| test_dedupe_migrates_notes_blogger_city | seed 关联数据 | 关联迁移到 canonical |
| test_dedupe_is_idempotent | 跑两遍 | 第二次 counts 不变 |

## 5. 验收

- 测试 3 案例全过；
- 在实际生产 DB 上跑 `python -m scripts.dedupe_cities --execute`：
  - `SELECT COUNT(*) FROM cities` 下降；
  - 城市下拉不再出现重复；
  - 推文/博主关联保持。
