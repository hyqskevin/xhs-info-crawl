# OPENCLI_BIN 配置化 + 任务启动预检 — 设计

日期：2026-07-27
关联事件：2026-07-27 定时任务 17 个博主全部抓取失败（`[Errno 2] No such file or directory: 'opencli'`）
根因：worker 由不含 nvm bin 目录的 shell 重启，PATH 中找不到 opencli（二进制位于 `~/.nvm/versions/node/v22.18.0/bin/opencli`）

## 1. 问题

1. `OpenCLIAdapter.run()` 硬编码 `['opencli', *args]`，二进制位置完全依赖 worker 进程 PATH；
2. 找不到二进制时每个关键词/博主各报一条原始 `Errno 2`，任务报文不可读，用户无法定位是环境问题；
3. worker 重启环境不可控（nohup / 不同 shell），同类故障会复发。

## 2. 设计

### 2.1 配置项

- `Settings.opencli_bin: str = "opencli"`（env `OPENCLI_BIN`）；
- 默认值保持现状（PATH 解析）；PATH 不可控的环境可配置绝对路径，如
  `OPENCLI_BIN=/Users/kevin_w/.nvm/versions/node/v22.18.0/bin/opencli`；
- `.env.example` 补说明。

### 2.2 适配器改造（`opencli_adapter.py`）

- `__init__` 保存 `self._bin = (settings.opencli_bin or "opencli").strip() or "opencli"`；
- `run()` 用 `[self._bin, *args]`；
- `subprocess.Popen` 抛 `FileNotFoundError` 时转成 `OpenCLIError`，报文含 bin 路径与修复指引：
  `opencli 不可用：未找到命令 '<bin>'（请运行 npm install -g @jackwener/opencli 或在 .env 配置 OPENCLI_BIN 指向其绝对路径）`；
- 该兜底覆盖所有调用方（抓取、enrich、设置页测试连接）。

### 2.3 任务启动预检（`crawl_task.py`）

- 模块级 `find_opencli(bin_name)` 包装 `shutil.which`（测试可 patch）；
- `run_crawl` claim 任务后、创建 adapter 前预检：找不到则
  - `task.status = FAILED`，`error_message` = 上述指引报文，`finished_at` 落时间，写 ERROR 日志，直接返回；
  - 不进搜索循环、不消耗周配额、不产生 N 条重复报错。

### 2.4 测试环境

- conftest 新增 autouse fixture：默认把 `crawl_task.find_opencli` patch 为返回 fake 路径
  （与 `fast_rate_limit_sleep` / `forbid_undeclared_celery_dispatch` 同风格），
  避免既有 run_crawl 集成测试在无 opencli 的开发机上全挂；
- 失败用例显式重 patch 为 `None`。

## 3. TDD 计划（先红）

`tests/test_opencli_bin.py`：

1. Settings 默认 `opencli`，构造参数覆盖生效；
2. adapter 用配置的 bin 调 Popen（断言 argv[0]）；
3. bin 不存在时 `OpenCLIError` 报文含路径与指引（非原始 Errno 2）；
4. run_crawl 预检失败：task FAILED + 指引报文 + ERROR 日志 + adapter 未被实例化；
5. run_crawl 预检通过路径：find_opencli 被调用且任务正常进入搜索（既有集成测试保持绿）。

## 4. 验收

- 上述测试先红后绿；后端全量测试绿；
- `docs/crawler-design.md` 补 OPENCLI_BIN 说明与"重启 worker 需保证 opencli 可解析"提示；
- 改动 `app/services/*.py`：完成后重启 celery worker 与 beat；
- 可选：本机 `.env` 配置 `OPENCLI_BIN` 绝对路径后，worker 无论以何种 shell 重启都能找到 opencli。

## 5. 非目标

- 不自动安装 opencli；
- 不检测 opencli 版本/登录态（whoami 检查已有 PAUSED 流程覆盖）。
