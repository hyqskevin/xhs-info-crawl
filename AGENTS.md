# 项目工作流程（Agent 工作约定）

> 本文件记录 AI 协作流程的硬约束。每次会话开始时必须先读本文件再行动。

## 核心规则

### 1. spec 过审 → 才能开发

每条 TODO 必须按以下顺序：

```
TODO 提出
    ↓
先解答问题（如果用户问"为什么"）
    ↓
写 spec（docs/superpowers/specs/<日期>-<slug>-design.md）
   含：目标、设计、验收
    ↓
spec 过用户审核（用户明确同意才能继续）
    ↓
写 TDD 测试（先写测试，让它失败）
   - 后端：backend/tests/test_*.py
   - 前端：frontend/src/**/*.spec.ts
   - E2E：tests/test-*.md
    ↓
实现代码（让测试通过）
    ↓
更新 docs/TODO.md（完成的标 [x]，然后移入"已完成"区）
```

**任何代码改动前必须有 spec；任何 spec 必须过用户审核。**

### 2. TDD 是测试驱动的开发

- 测试**先写**，先看到失败（红）
- 再写实现，看到通过（绿）
- 再重构
- 单元测试和 E2E 测试都要写
- 不写测试不算完成

### 3. 提问与回答

如果用户问"为什么"或质疑"问题原因"：
- **先排查证据**（看代码、看日志、看 DB）
- **找到真正根因**（不止表面现象）
- **给方案**（不止"延长超时"等 workaround）
- **过用户审核**才动代码

### 4. TODO 流程

每条 TODO 必须出现在 `docs/TODO.md`：
- 当前待办：`- [ ]` 描述 + 目标 + 验收
- 完成后：移入"已完成"区，标 `[x]`，保留目标/验收描述
- 不直接删除，便于追踪

### 5. 撤销不符合规则的代码

任何**未过审的 spec、未完成的 TDD**：
- 立即撤掉实现
- 撤掉 spec（如果用户否决）
- 不偷偷保留

## 文件约定

| 文件 | 用途 |
|---|---|
| `docs/TODO.md` | 唯一待办入口 |
| `docs/superpowers/specs/<日期>-<slug>-design.md` | 每条 TODO 的 spec |
| `docs/api-doc.md` | API 文档 |
| `docs/database-design.md` | 数据库设计 |
| `docs/ui-design.md` | UI 设计 |
| `docs/crawler-design.md` | 爬虫设计 |
| `docs/architecture.md` | 架构 |
| `backend/tests/test_*.py` | 后端单元/集成测试 |
| `frontend/src/**/*.spec.ts` | 前端组件测试 |
| `frontend/e2e/*.spec.ts` | 前端 E2E |
| `tests/test-*.md` | 测试案例文档 |

## 测试命令

```bash
make test                           # 全量
cd backend && pytest -q             # 后端
cd frontend && npm run test -- --run  # 前端
```

## 提交约定

- 改动经过 spec + TDD + 测试通过后才能提交
- 不提交无 spec 的代码
- 每个 commit 关联一条 TODO 项
