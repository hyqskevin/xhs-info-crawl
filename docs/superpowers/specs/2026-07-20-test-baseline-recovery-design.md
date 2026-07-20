# 全量测试基线恢复设计

## 状态

已于 2026-07-20 经用户确认，可以进入实施计划与 TDD 阶段。

## 目标

恢复一套可重复执行、不会意外调用真实外部工具的项目测试基线，使后续抓取稳定性、数据正确性和周报修复都有可信的回归验证基础。

完成本项后，以下命令必须能够正常结束并返回退出码 0：

```bash
cd backend && pytest -q
cd frontend && npm run test -- --run
cd frontend && npm run build
git diff --check
```

## 问题证据与根因

### 后端测试会调用真实 OpenCLI

`backend/tests/test_opencli_and_dedup_integration.py` 中的 `test_run_translates_missing_url_error` 仍替换 `subprocess.run`。当前 `OpenCLIAdapter.run()` 已改为通过 `subprocess.Popen` 启动命令，因此旧替身不会生效。

执行该测试时会实际运行 `opencli browser ...`，并等待适配器命令超时。这既使单测卡住，也会依赖本地 Chrome、登录状态和 OpenCLI 环境，破坏测试的可重复性。

### 当前全量结果不可作为交付依据

后端测试被上述用例阻塞；前端测试执行未得到完整的成功退出结果。缓存中的历史结果或部分通过输出都不能证明当前工作区全量通过。

### 工作区存在大量既有改动

测试恢复必须保留当前已修改和未跟踪文件，不得通过 reset、checkout、批量覆盖或顺带重构来获得“干净”结果。验收只关注本项引入的差异和测试结论，不要求擅自清理用户改动。

## 设计原则

1. **测试隔离外部边界**：后端单元测试不得启动真实 OpenCLI、Chrome、浏览器标签页或网络请求。
2. **匹配当前接口**：测试替身应模拟 `subprocess.Popen` 对象实际被适配器使用的最小接口，而不是恢复已废弃的 `subprocess.run` 实现。
3. **不改变业务行为**：本项只修复测试和测试基础设施；不得为了让测试通过而回退 `Popen`、改变抓取逻辑或放宽断言。
4. **保护既有改动**：只修改本 spec 明确涉及的文件；不重置、不删除、不格式化无关文件。
5. **结果以进程退出码为准**：测试报告必须记录命令、退出码、通过/失败数量和耗时，不以缓存文件或截断输出代替。

## 设计方案

### 1. 修复 OpenCLI 子进程测试替身

在 `backend/tests/test_opencli_and_dedup_integration.py` 内提供最小 `FakePopen`：

- 构造时记录命令参数；
- 暴露 `pid` 和 `returncode`；
- `communicate(timeout=...)` 返回预设的 stdout、stderr；
- `kill()` 记录终止动作；
- 能模拟正常返回、`Missing url`、登录失败和超时等当前用例需要的结果。

目标用例改为替换 `subprocess.Popen`，并断言错误翻译结果。测试中若意外走到真实 `Popen`，应立即失败，而不是等待外部命令超时。

如果项目中已有等价测试替身，则复用现有实现，不重复建立第二套抽象。

### 2. 审计外部调用隔离

检查后端测试中对以下入口的替换是否仍匹配生产实现：

- `subprocess.Popen`；
- OpenCLI adapter 的 `run()`；
- HTTP/模型/OCR 客户端；
- Celery 任务派发。

发现测试会真实访问外部资源时，只修正测试替身。若发现生产代码本身存在业务缺陷，新增独立 TODO 和 spec，不并入本项。

### 3. 分层恢复测试基线

按以下顺序执行，以便快速定位失败层级：

1. 单独运行原卡死用例，确认它能快速结束并通过；
2. 运行相关 OpenCLI、任务停止测试；
3. 运行完整后端测试；
4. 运行完整前端组件测试；
5. 运行前端生产构建；
6. 运行 `git diff --check`。

如果前端或后端全量测试暴露与本项无关的业务失败，记录实际错误并新增 TODO，不使用跳过、删除断言或扩大 mock 范围掩盖失败。

### 4. 工作区保护与结果报告

开始实施前记录相关文件的 `git status --short`。完成后只报告本项修改的文件，并核对其他已修改、未跟踪文件仍被保留。

最终测试报告至少包含：

- 每条验收命令；
- 退出码；
- 测试通过、失败和跳过数量；
- 命令耗时；
- 未纳入本项但新发现的问题。

## 文件范围

预计修改：

- `backend/tests/test_opencli_and_dedup_integration.py`

仅在发现其他测试存在同类失效替身时，允许修改对应的 `backend/tests/test_*.py` 或 `frontend/src/**/*.spec.ts`。不得修改 `backend/app/**`、`frontend/src` 非测试代码或数据库文件；如果确需修改，必须先新增独立 TODO/spec 并重新过审。

文档变更：

- `docs/TODO.md`
- `docs/superpowers/specs/2026-07-20-test-baseline-recovery-design.md`

## TDD 与验证要求

本项修复的是测试基础设施，因此红灯证据采用“旧测试在当前实现下启动真实 OpenCLI并卡住/超时”。实施时先用单用例复现该现象，再替换测试替身，并验证：

1. 单用例不调用真实 OpenCLI；
2. `Missing url` 错误仍被正确转换为 `OpenCLIError`；
3. 相关 Popen 注册、终止和超时测试没有回退；
4. 全量测试与构建均通过。

本项不新增浏览器 E2E 场景，因为不改变用户界面或业务流程。真实 OpenCLI 登录与抓取验证继续由现有真实任务 TODO 单独执行，不能混入离线单元测试。

## 验收条件

1. `test_run_translates_missing_url_error` 在未安装或不可用 OpenCLI 时仍能快速通过。
2. 后端测试期间没有创建真实 OpenCLI/Chrome 子进程，也没有网络访问。
3. `cd backend && pytest -q` 正常结束，退出码为 0。
4. `cd frontend && npm run test -- --run` 正常结束，退出码为 0。
5. `cd frontend && npm run build` 正常结束，退出码为 0。
6. `git diff --check` 无错误。
7. 未删除、重置或覆盖本项开始前已存在的用户改动。
8. 完成后将本 TODO 移入 `docs/TODO.md` 的“已完成”区，并保留目标、验收和测试结果。

## 非目标

- 不处理 OpenCLI 真实运行超时、登录恢复或验证码流程；
- 不修改任务停止状态机或 PID 安全机制；
- 不清洗 SQLite 历史活动数据；
- 不修复周报唯一键、城市映射或快照一致性；
- 不轮换 MiniMax API Key；
- 不把当前所有未提交改动合并成一次提交。

这些问题继续作为独立事项按 TODO → spec → 审核 → TDD → 实现的流程推进。
