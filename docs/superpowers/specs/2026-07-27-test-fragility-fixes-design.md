# 测试脆弱性修复 — 设计 spec

> 对应 `docs/TODO.md` 待办 #10。

## 背景

1. `backend/tests/test_poster_task_api.py::test_render_with_mocked_opencli` 在无 opencli 的机器上 503：用例 mock 了 `subprocess.run`，但 `poster_renderer.py:231` 前置 `shutil.which("opencli")` 未 mock，找不到 opencli 直接 RuntimeError。该用例长期占据「全量唯一失败」。
2. `frontend/src/views/PostersListView.spec.ts` 的「navigates to wizard」用例：组件模板 `:60` 直接 `$router.push('/posters/new')`，mount 未注入 router，点击后 TypeError 成为未捕获错误（测试自身 pass 但 Vitest 报 `Errors 1 error`）。原用例注释自承「简化：只验证没报错」——实际有报错且断言无意义。

## 设计

1. 后端用例补 `shutil.which` mock：`opencli` 返回假路径，其余（`python3` 等）透传真实 which（Popen http.server 未被 mock，仍需真实解释器）。
2. 前端 spec：`factory()` 的 `global.mocks` 注入 `$router: { push }` spy；「navigates to wizard」断言 `push` 以 `'/posters/new'` 被调，消除未捕获 TypeError 并使断言有效。

## 验收

- 无 opencli 环境下后端全量零失败；
- 前端 `npm run test -- --run` 全过且零 `Errors`。
