# 海报生成开发与测试落地清单

> 这份文档明确：哪些写在 spec（`docs/superpowers/specs/...`）；哪些真的落了；哪些是 mock / 端到端；还差什么。
> 本节用于核对"测试文档完整性"。

## 1. 已实施（写了代码 + 测试）

### 1.1 后端单元测试

| 文件 | case | 说明 |
|---|---|---|
| `backend/tests/test_poster_models.py` | 5 | UNIQUE / parsed_meta / items / RESTRICT / 默认 status |
| `backend/tests/test_poster_template_api.py` | 9 | CRUD + AI parse-from-image（mock MiniMaxClient.vision_chat） |
| `backend/tests/test_poster_task_api.py` | 7 | CRUD + preview + candidates + render（mock subprocess.run） |

总计 **21 case**，**全部离线（mock）运行**，不需要 opencli / playwright / chromium 装好。

### 1.2 后端 E2E 回放脚本（API 层）

| 文件 | 场景 |
|---|---|
| `tests/scripts/test_poster_generation.sh` | 登录拿 token → 模板 CRUD（1.1-1.4）→ 任务流程（2.1-2.6） |

依赖：dev API 跑起来（`make dev-api`），admin 账号存在。
**不依赖** opencli / playwright。

### 1.3 数据迁移

| 文件 | 说明 |
|---|---|
| `backend/migrations/versions/0014_poster_models.py` | 2 张新表 |
| `backend/app/models/poster.py` | ORM |

生产 DB 已 alembic 升级到 0014（实测）。

## 2. spec 提到但**未落测试**的部分

### 2.1 后端 render 真实集成（spec §5 + §6.2.6）

按 spec §5.1-5.2：
- Playwright 优先；
- opencli fallback（两步命令）；
- 真实 PNG 落 `data/posters/{task_id}.png`。

**当前状态**：单元测试用 `monkeypatch` 替换 `subprocess.run` 假装写 PNG。
**未实施**：
- 没有"启动 http.server + opencli 真截图"的脚本；
- 没断言"产物 PNG magic 8 bytes 正确"。

**已补的下一步**：见 §3.1。

### 2.2 前端 View 测试（spec §6.2）

| 文件 | case |
|---|---|
| `frontend/PostersListView.spec.ts` | 3（任务列表 / 状态分组 / 删除/再生成） |
| `frontend/PosterWizardView.spec.ts` | 4（6 步导航 / 候选筛选 / 模板切换 / 预览同步） |
| `frontend/PosterTemplateSettings.spec.ts` | 3（模板列表 / 上传解析 / 编辑保存） |

**当前状态**：未实施。

### 2.3 前端 E2E（spec §3.2 / §5）

`frontend/e2e/poster-flow.spec.ts`：模拟浏览器跑 wizard 6 步 + 截图。
**当前状态**：未建文件。

### 2.4 视觉回归（spec §5）

`tests/baselines/poster-baseline.png`：固定一张基准海报 PNG；E2E 截图与之像素 diff ≤ 0.5%。
**当前状态**：未建 baseline 文件、未建 diff 比较脚本。

## 3. 接下来要补的 md 文档（含脚本）

### 3.1 已补：spec→落地映射

本文件即该映射。

### 3.2 待补（按你之前的指示：补 md）

| 文件 | 内容 |
|---|---|
| `docs/poster-getting-started.md` | 第一次用：配 MINIMAX_API_KEY、上传第一张海报、生成第一张图 |
| `tests/scripts/test_poster_real_render.sh` | 启 http.server、调 API、opencli 真截图、PNG magic 断言 |
| `tests/scripts/test_poster_opencli_integration.sh` | 真实 opencli 路径（启 server + screenshot + 解 base64 → 写 PNG） |

## 4. 测试矩阵

| 测试类型 | CI 是否要 | 数量 | 状态 |
|---|---|---|---|
| 单元（后端 pytest） | ✅ | 21 | ✅ 全绿 |
| API 回放 bash | ✅（dev 启动后） | 11 场景 | ✅ |
| 真实 render 集成 | ❌ dev only | — | ❌ 未建 |
| 前端 View（vitest） | ✅ | 10（plan） | ❌ 未建 |
| 前端 E2E（Playwright） | ❌ dev only | — | ❌ 未建 |
| 视觉回归（baseline diff） | ❌ dev only | — | ❌ 未建 |

## 5. 现状快照

- 后端：357 passed, 1 skipped
- 前端：48 passed
- 后端依赖：python-multipart（dev 已 install）；未装 Pillow / Playwright / opencli system-wide（opencli 已装在 dev 机器）
- E2E bash：API 层已写；opencli 真实路径仅 spec 描述，未实现脚本
