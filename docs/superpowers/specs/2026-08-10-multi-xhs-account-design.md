# 多小红书账号配置 + 抓取失效自动切换

## 1. 背景

用户 2026-07-28 提出需求：支持配置多个小红书账号（抓取用登录态），抓取时优先用主账号；某账号失效（未登录/扫码超时/被风控）时自动切换到下一个可用账号继续，全部失效才 PAUSED 等人工处理。

## 2. 对齐结论（2026-08-10）

1. **账号隔离**：多 Chrome profile（每个账号一个独立 session 名，opencli `browser <session> ...` 命令天然隔离）
2. **失效判定**：复用现有 `AuthenticationRequired`（未登录/扫码超时）+ `VerificationRequired`（风控验证），不细分
3. **切换粒度**：笔记级切换（账号A失效后，下一篇笔记立即切到账号B，不重抓已完成笔记）

## 3. 目标

- 配置中心新增「账号配置」tab，CRUD 多个小红书账号
- 抓取任务启动时按优先级排序账号，主账号优先
- 运行中某账号 `AuthenticationRequired`/`VerificationRequired` 时，下一篇笔记自动切到下一个账号
- 全部账号失效才进入现有 PAUSED + 扫码引导流程
- 切换时记 INFO 日志（"账号 A 失效，切换到账号 B"）

## 4. 设计

### 4.1 数据模型

新表 `xhs_accounts`：
```python
class XhsAccount(Base):
    __tablename__ = "xhs_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))  # 账号名称（如"主账号"）
    remark: Mapped[str] = mapped_column(String(256), default="")  # 备注
    session_name: Mapped[str] = mapped_column(String(64), unique=True)  # opencli session 名（如"xhs-main"）
    login_status: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown/logged_in/logged_out
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 越小越优先，0=最高
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
```

migration `0019_xhs_accounts.py`。

### 4.2 API

```
GET    /api/v1/xhs-accounts           列表（按 priority 排序）
POST   /api/v1/xhs-accounts           创建
PUT    /api/v1/xhs-accounts/{id}      更新（name/remark/enabled/priority）
DELETE /api/v1/xhs-accounts/{id}      删除
POST   /api/v1/xhs-accounts/{id}/check-login   检查登录状态（调 opencli whoami）
```

### 4.3 抓取流程改造

**run_crawl 启动时**：
1. 查询 `xhs_accounts` 表，按 priority 排序，取 enabled 账号列表
2. 如果无账号配置，回退当前行为（用默认 session 'xhs-crawler'）
3. 如果有账号，用第一个账号的 session_name 初始化 OpenCLIAdapter

**笔记级切换**：
```python
# run_crawl 主循环
account_index = 0
accounts = load_xhs_accounts(db, enabled_only=True)  # 按 priority 排序
if not accounts:
    accounts = [DefaultAccount(session_name='xhs-crawler')]

adapter = OpenCLIAdapter(settings, session=accounts[0].session_name)
adapter.bind_task(task.id, ...)

for entry in results:
    try:
        staged = download_and_ocr(db, task, run_token, ..., adapter, settings)
        ...
    except AuthenticationRequired as exc:
        # 当前账号失效，尝试切换
        account_index += 1
        if account_index < len(accounts):
            new_account = accounts[account_index]
            log(db, task.id, "INFO", f"账号 {accounts[account_index-1].name!r} 失效，切换到 {new_account.name!r}")
            adapter = OpenCLIAdapter(settings, session=new_account.session_name)
            adapter.bind_task(task.id, ...)
            # 重试当前笔记
            staged = download_and_ocr(db, task, run_token, ..., adapter, settings)
        else:
            # 全部账号失效，进入 PAUSED
            raise CrawlHalted("所有账号均已失效，请扫码登录后继续")
    except VerificationRequired as exc:
        # 风控验证，同样切换账号
        ...
```

### 4.4 前端

**配置中心新增「账号配置」tab**（SettingsView.vue）：
- 账号列表表格（名称/备注/session名/登录状态/启用/优先级）
- 新增/编辑/删除账号
- "检测登录"按钮（调 check-login 端点）

**DashboardView 发起抓取**：
- 新增「操作账号」下拉（可选，默认按 priority 自动选）
- 不传则用默认行为（按 priority 排序自动选第一个）

### 4.5 兼容性

- 无 xhs_accounts 数据时，回退默认 session 'xhs-crawler'，行为不变
- 现有任务参数不强制 xhs_account_id，向后兼容

## 5. 验收

- [ ] 新表 `xhs_accounts` + migration 0019
- [ ] CRUD API `/xhs-accounts` + check-login 端点
- [ ] run_crawl 启动时加载账号列表，按 priority 排序
- [ ] 笔记级切换：AuthenticationRequired/VerificationRequired 时切下一个账号
- [ ] 全部账号失效才 PAUSED
- [ ] 切换时记 INFO 日志
- [ ] 无账号配置时回退默认 session
- [ ] 配置中心新增「账号配置」tab
- [ ] DashboardView 新增「操作账号」下拉（可选）
- [ ] TDD 测试覆盖
- [ ] 后端全量测试通过，前端全量测试 + build 通过
- [ ] **worker 重启后实测**

## 6. 部署

- migration `alembic upgrade head`
- **worker 必须重启**
- uvicorn `--reload` 自动加载 API 层
- 前端 dev server 自动刷新

## 7. 与 TODO#88 的关系

TODO#88「仪表盘抓取前先选定操作账号 + 扫码登录确认」是本条配套：
- 本条（TODO#49）：运行中自动切换
- TODO#88：启动前预检 + 选定账号

两者共用同一份 XhsAccount 配置。开发顺序：先做本条（自动切换），再做 TODO#88（启动前预检）。
