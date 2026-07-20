# 全量测试基线恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复失效的 OpenCLI 子进程测试替身，并用明确退出码恢复后端测试、前端组件测试、前端构建和差异检查的可信基线。

**Architecture:** 保留生产代码当前的 `subprocess.Popen` 实现，只在测试边界模拟 `Popen` 返回对象。先用 fail-fast 替身证明旧 `subprocess.run` mock 已失效，再换成最小 `FakeProc`，最后按后端相关测试、后端全量、前端全量、生产构建和 Git 差异检查分层验收。

**Tech Stack:** Python 3.11+、pytest、monkeypatch、Vue 3、Vitest、TypeScript、Vite。

## Global Constraints

- 不修改 `backend/app/**` 或任何前端非测试业务代码。
- 后端单元测试不得启动真实 OpenCLI、Chrome、浏览器标签页或网络请求。
- 不得通过跳过测试、删除断言、放宽断言或回退 `Popen` 实现获得绿灯。
- 不得 reset、checkout、删除、覆盖或批量格式化工作区中已有的用户改动。
- `backend/tests/test_opencli_and_dedup_integration.py` 在本任务开始前已是 modified；未经用户单独确认，不整文件暂存或提交。
- 与本项无关的业务失败必须新增独立 TODO/spec，本计划中停止扩展实现范围。
- 测试结论必须来自本次命令的完整输出与退出码，不读取缓存结果代替。

---

### Task 1: 记录工作区边界并复现失效测试替身

**Files:**
- Inspect: `backend/tests/test_opencli_and_dedup_integration.py:117-128`
- Inspect: `backend/app/services/opencli_adapter.py:26-73`
- Modify: `backend/tests/test_opencli_and_dedup_integration.py:117-128`

**Interfaces:**
- Consumes: `OpenCLIAdapter.run(args: list[str], *, task_id: int | None = None) -> Any`，内部调用 `subprocess.Popen(...).communicate(timeout=...)`。
- Produces: 一份可快速结束的红灯证据，证明替换 `subprocess.run` 已无法隔离当前实现。

- [ ] **Step 1: 记录实施前相关文件状态**

Run:

```bash
git status --short -- backend/tests/test_opencli_and_dedup_integration.py backend/app/services/opencli_adapter.py docs/TODO.md docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md
```

Expected: 测试、适配器和 TODO 的既有 modified 状态被记录；不得据此清理任何文件。

- [ ] **Step 2: 在原用例加入 fail-fast `Popen` 替身形成红灯**

将目标用例临时改成以下内容。保留旧 `subprocess.run` mock，同时让当前实现一旦调用 `Popen` 就立即失败，避免启动真实 OpenCLI：

```python
def test_run_translates_missing_url_error(tmp_path: Path, monkeypatch):
    from app.services.crawler import OpenCLIError

    adapter = OpenCLIAdapter(Settings(project_root=tmp_path))
    fake_result = type(
        "R",
        (),
        {"stdout": "", "stderr": "✖  Missing url\n", "returncode": 1},
    )()

    def fail_if_popen_is_used(*args, **kwargs):
        raise AssertionError("stale test double: adapter uses subprocess.Popen")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_result)
    monkeypatch.setattr(subprocess, "Popen", fail_if_popen_is_used)

    try:
        adapter.run(["browser", adapter.session, "open", "", "--window", "background"])
    except OpenCLIError as exc:
        message = str(exc)
        assert "Missing url" in message or "缺少 url" in message
    else:
        raise AssertionError("expected OpenCLIError for missing url from opencli")
```

- [ ] **Step 3: 运行单用例验证红灯快速出现**

Run:

```bash
cd backend && pytest -q tests/test_opencli_and_dedup_integration.py::test_run_translates_missing_url_error
```

Expected: FAIL，错误包含 `stale test double: adapter uses subprocess.Popen`；命令应在数秒内结束且没有真实 OpenCLI 进程。

---

### Task 2: 用最小 `FakeProc` 修复 Popen 测试边界

**Files:**
- Modify: `backend/tests/test_opencli_and_dedup_integration.py:117-128`
- Reference: `backend/tests/test_adapter_popen_register.py:27-58`

**Interfaces:**
- Consumes: `subprocess.Popen(command, stdout=PIPE, stderr=PIPE, text=True)`；返回对象必须提供 `pid: int`、`returncode: int`、`communicate(timeout: int) -> tuple[str, str]` 和 `kill() -> None`。
- Produces: 离线的 `test_run_translates_missing_url_error`，验证命令使用 `opencli` 且 `Missing url` 被翻译为 `OpenCLIError`。

- [ ] **Step 1: 将 fail-fast 红灯替换成完整的最小测试替身**

将目标用例替换为：

```python
def test_run_translates_missing_url_error(tmp_path: Path, monkeypatch):
    from app.services.crawler import OpenCLIError

    adapter = OpenCLIAdapter(Settings(project_root=tmp_path))
    popen_calls: list[tuple[list[str], dict]] = []

    class FakeProc:
        pid = 12345
        returncode = 1

        def communicate(self, timeout=None):
            return "", "✖  Missing url\n"

        def kill(self):
            return None

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    try:
        adapter.run(["browser", adapter.session, "open", "", "--window", "background"])
    except OpenCLIError as exc:
        message = str(exc)
        assert "Missing url" in message or "缺少 url" in message
    else:
        raise AssertionError("expected OpenCLIError for missing url from opencli")

    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command == [
        "opencli",
        "browser",
        adapter.session,
        "open",
        "",
        "--window",
        "background",
    ]
    assert kwargs["text"] is True
```

- [ ] **Step 2: 运行单用例验证绿灯**

Run:

```bash
cd backend && pytest -q tests/test_opencli_and_dedup_integration.py::test_run_translates_missing_url_error
```

Expected: `1 passed`，退出码 0，数秒内结束。

- [ ] **Step 3: 审计后端测试中的外部进程与网络边界**

Run:

```bash
rg -n "subprocess\.(run|Popen)|OpenCLIAdapter|httpx\.|requests\." backend/tests
```

Expected:

- `test_opencli_and_dedup_integration.py` 的目标用例替换 `subprocess.Popen`；
- `test_adapter_popen_register.py` 中的适配器用例均替换 `subprocess.Popen`；
- `test_minimax.py` 使用 `httpx.MockTransport`；
- `test_worker_stop_during_block.py` 和 `test_task_stop_immediate.py` 仅为 PID 停止测试启动本地 `sleep`，不调用 OpenCLI、Chrome 或网络；
- 没有其他未隔离的 OpenCLI 或 HTTP 调用。若发现新的未隔离入口，停止本任务并为对应测试新增独立 TODO/spec。

- [ ] **Step 4: 运行 OpenCLI 与停止任务相关回归测试**

Run:

```bash
cd backend && pytest -q tests/test_opencli_and_dedup_integration.py tests/test_adapter_popen_register.py tests/test_worker_stop_during_block.py tests/test_task_stop_immediate.py
```

Expected: 所有收集到的测试通过，退出码 0；无真实 OpenCLI 或 Chrome 进程被创建。

---

### Task 3: 验证完整后端测试基线

**Files:**
- Test: `backend/tests/test_*.py`
- Do not modify: `backend/app/**`

**Interfaces:**
- Consumes: Task 2 修复后的 Popen 测试替身。
- Produces: 当前工作区完整后端测试的退出码、通过/失败/跳过数量和耗时。

- [ ] **Step 1: 运行完整后端测试并显示慢用例**

Run:

```bash
cd backend && pytest -q --durations=10
```

Expected: pytest 正常结束，退出码 0；记录最终 summary 中的 passed、skipped 数量和总耗时。

- [ ] **Step 2: 对失败结果执行范围判定**

若 Step 1 失败，只允许以下处理：

```text
测试替身仍与当前外部接口不匹配：回到 Task 2，最小修正对应测试替身。
生产业务行为或数据断言失败：停止实施，在 docs/TODO.md 新增独立事项并先写 spec。
环境依赖缺失：记录缺失命令或依赖，不修改业务代码绕过。
```

Expected: 不使用 `pytest.skip`、删除用例、放宽断言或修改生产代码掩盖失败。

---

### Task 4: 验证完整前端测试与生产构建

**Files:**
- Test: `frontend/src/**/*.spec.ts`
- Build input: `frontend/src/**`
- Do not modify: `frontend/src` 中的非测试文件

**Interfaces:**
- Consumes: 当前 Vue 3、Vitest、TypeScript 和 Vite 配置。
- Produces: 前端组件测试与生产构建的退出码、测试数量和耗时。

- [ ] **Step 1: 运行完整前端组件测试**

Run:

```bash
cd frontend && npm run test -- --run
```

Expected: Vitest 正常结束，退出码 0；记录 test files、tests 和 duration 汇总。

- [ ] **Step 2: 运行 TypeScript 检查与生产构建**

Run:

```bash
cd frontend && npm run build
```

Expected: `vue-tsc --noEmit` 和 `vite build` 均成功，退出码 0；记录构建耗时。

- [ ] **Step 3: 对前端失败结果执行范围判定**

若组件测试或构建失败，只允许以下处理：

```text
测试文件仍引用已经变更的公开组件接口：记录证据并判断是否属于纯测试替身问题。
组件行为、路由、API 类型或构建代码失败：停止实施，在 docs/TODO.md 新增独立事项并先写 spec。
不得在本计划内修改前端业务代码。
```

Expected: 本项不借机更改 UI、路由、API 或业务逻辑。

---

### Task 5: 完成差异检查、TODO 归档和测试报告

**Files:**
- Modify: `docs/TODO.md:15-17`
- Inspect: all files changed by this task

**Interfaces:**
- Consumes: Tasks 2-4 的完整命令输出和退出码。
- Produces: 无格式错误的最终差异、归档后的 TODO 和可复核的测试结果摘要。

- [ ] **Step 1: 检查本任务差异与空白错误**

Run:

```bash
git diff --check
git diff -- backend/tests/test_opencli_and_dedup_integration.py docs/TODO.md docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md docs/superpowers/plans/2026-07-20-test-baseline-recovery.md
```

Expected: `git diff --check` 退出码 0；差异中没有业务代码改动，没有用户文件被删除或重置。

- [ ] **Step 2: 将本项从当前待办移入已完成区**

从“当前待办”删除以下三行：

```markdown
- [ ] 恢复可重复执行的全量测试基线
  - 目标：修复测试与当前 `subprocess.Popen` 实现不一致导致的真实 OpenCLI 调用和卡死，在不改业务行为、不覆盖现有工作区改动的前提下，恢复后端、前端组件测试与前端构建的稳定验收能力。
  - 验收：`cd backend && pytest -q`、`cd frontend && npm run test -- --run`、`cd frontend && npm run build` 均正常结束且退出码为 0；测试过程不启动真实 OpenCLI、Chrome 或网络请求；`git diff --check` 无错误；关联 spec：`docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md`。
```

在“已完成”末尾追加：

```markdown
- [x] 恢复可重复执行的全量测试基线
  - 目标：修复测试与当前 `subprocess.Popen` 实现不一致导致的真实 OpenCLI 调用和卡死，在不改业务行为、不覆盖现有工作区改动的前提下，恢复后端、前端组件测试与前端构建的稳定验收能力。
  - 验收：后端全量测试、前端组件测试、前端生产构建和 `git diff --check` 均正常结束且退出码为 0；测试过程未启动真实 OpenCLI、Chrome 或网络请求。
  - 关联：spec `docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md`；plan `docs/superpowers/plans/2026-07-20-test-baseline-recovery.md`。
```

- [ ] **Step 3: 复核工作区保护条件**

Run:

```bash
git status --short
```

Expected: 实施前已有的 modified/untracked 文件仍存在；本任务只新增 plan，并修改 spec 状态、目标测试用例和 TODO 项。

- [ ] **Step 4: 输出最终测试报告**

最终回复采用以下固定结构，并填入 Tasks 3-4 实际输出中的精确数字：

```text
后端：退出码、passed、skipped、耗时
前端测试：退出码、test files、tests、耗时
前端构建：退出码、耗时
差异检查：退出码
外部隔离：是否启动真实 OpenCLI/Chrome/网络
新发现问题：无，或对应 TODO/spec 路径
```

Expected: 每个结果都有本次运行输出支持，不引用 `.pytest_cache` 或 Vitest 缓存。

## 提交说明

本计划不自动执行 `git add` 或 `git commit`。原因是 `backend/tests/test_opencli_and_dedup_integration.py` 与 `docs/TODO.md` 在本任务开始前已有未提交改动，整文件暂存会混入用户内容。测试全部通过后，只报告本任务差异；如用户要求提交，再单独确认提交范围并采用可审查的部分暂存方式。
