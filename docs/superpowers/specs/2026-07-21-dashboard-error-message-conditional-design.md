# 仪表盘 last_task.error_message 条件渲染设计

> 状态：审核中。

## 1. 目标

仪表盘进度卡片当前**无条件**渲染 `last_task.error_message`，导致：

- 任务 `status='COMPLETED_WITH_ERRORS'`（某条笔记一次性报错）仍把这条 error_message 显示给用户，
- 用户误以为"还在报错"。

改为：**仅当 `status ∈ {RUNNING, FAILED, PAUSED, STOPPED, STOP_REQUESTED}` 时显示 error_message**。

`COMPLETED` / `COMPLETED_WITH_ERRORS` 不显示（已完成任务，error 是历史上下文）。

## 2. 设计

### 2.1 前端

`DashboardView.vue` line 164：

```vue
<ElAlert v-if="shouldShowLastTaskError" :title="lastTask.error_message" ... />
```

加 `shouldShowLastTaskError` 计算属性：

```ts
const errorVisibleStatuses = ['RUNNING','STOP_REQUESTED','FAILED','PAUSED','STOPPED']
const shouldShowLastTaskError = computed(() =>
  !!lastTask.value?.error_message && errorVisibleStatuses.includes(lastTask.value.status)
)
```

**为什么不后端改？** 后端 schema 已经包含 error_message 字段，前端选择性展示语义最干净；减少前端/移动端/第三方调用方的耦合。

### 2.2 后端

**不改**。`tests/test_dashboard_summary.py` 如果还没有此覆盖，加 3 个 case：

1. last_task status=COMPLETED 时，summary 仍包含 error_message 字段（后端始终带），由前端决定显示；
2. last_task status=FAILED 时 summary 含 error_message；
3. last_task status=RUNNING 时 summary 含 error_message。

注：这些 case 后端已经隐式覆盖（dashboard 接口总是 dump 所有列）。我们仅在 spec 中重申"前端做条件渲染是正确路径"。

## 3. 前端测试

`frontend/src/views/DashboardView.spec.ts` 增加：

### 3.1 case A：status=COMPLETED_WITH_ERRORS 时不渲染 error_message

mock `api.dashboard()` 返回 `{ data: { data: { last_task: { ... status: 'COMPLETED_WITH_ERRORS', error_message: '一条笔记失败' } } } }`；
断言 wrapper.find('.el-alert--error').exists() === false。

### 3.2 case B：status=FAILED 时渲染 error_message

mock status='FAILED' + error_message='opencli 子进程崩溃'；
断言 wrapper.find('.el-alert--error').exists() === true，且文案含 'opencli 子进程崩溃'。

### 3.3 case C：status=RUNNING 时渲染 error_message

mock status='RUNNING' + error_message='等待下次重试'；
断言 wrapper.find('.el-alert--error').exists() === true。

## 4. 验收

- [ ] 后端 `tests/test_dashboard_summary.py` 若覆盖则加 3 个 case；
- [ ] 前端 `DashboardView.spec.ts` 加 3 个 case（A/B/C）；
- [ ] 全量前端 48+ 测试、`npm run build` 通过；
- [ ] Playwright 仪表盘 E2E：用 admin 账号登录 → 发起一项任务 → 在它 `COMPLETED_WITH_ERRORS` 时截图 → 进度卡片不显示红色 Alert；接着把 last_task 模拟为 FAILED → 截图 → 红色 Alert 出现。
