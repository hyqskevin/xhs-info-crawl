# P3 启动器 Python 后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现启动器 Python 后端:进程管理(API/Worker/Beat 子进程)、状态服务(本地 HTTP)、env bootstrap(.env 初始化/端口探测/敏感配置生成)、OpenCLI 测试、OCR 安装器。

**Architecture:** 启动器是独立 Python 包(`launcher/`),和后端共用便携 Python venv。各模块职责单一:`port_finder` 找可用端口;`env_bootstrap` 初始化 .env;`process_manager` 管理子进程;`opencli_checker` 测试 OpenCLI;`ocr_installer` 下载安装 OCR;`status_server` 提供 HTTP 状态接口;`main.py` 用 PyWebView 启动 UI。

**Tech Stack:** Python 3.11 + FastAPI(状态服务)+ subprocess(进程管理)+ httpx(下载)+ pywebview(UI 壳)

**Spec:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 2-5 + § 7.3 + § 13

---

## 文件结构

```
launcher/
├── __init__.py
├── main.py                  # PyWebView 启动入口
├── port_finder.py           # 端口探测(找可用端口)
├── env_bootstrap.py         # .env 初始化/敏感配置生成/缓存环境变量设置
├── process_manager.py       # 子进程管理(启停/心跳/日志)
├── opencli_checker.py       # OpenCLI 连接测试
├── ocr_installer.py         # OCR 增强包下载安装
├── status_server.py         # 本地状态 HTTP 服务
├── requirements.txt         # pywebview/fastapi/uvicorn/httpx
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_port_finder.py
    ├── test_env_bootstrap.py
    ├── test_process_manager.py
    ├── test_opencli_checker.py
    ├── test_ocr_installer.py
    └── test_status_server.py
```

---

## 执行策略

由于 P3 涉及 7 个模块,采用**分批派遣子代理**策略:

- **批次 1**:port_finder + env_bootstrap(独立模块,无依赖)
- **批次 2**:opencli_checker + ocr_installer(独立模块,无依赖)
- **批次 3**:process_manager(依赖 env_bootstrap 的环境变量设置)
- **批次 4**:status_server + main.py(依赖前面所有模块)

每个批次用 TDD:先写测试看到失败,再实现看到通过。

## 详细任务(每个模块的测试+实现代码见各批次子代理派遣)

### 批次 1:port_finder + env_bootstrap

**port_finder.py**:
- `find_available_port(start=8000, end=8020) -> int`:用 socket bind 探测可用端口
- 测试:跳过被占用端口、所有端口被占抛 RuntimeError、起始端口可用直接返回

**env_bootstrap.py**:
- `generate_secret_key() -> str`:32 字节随机 hex(64 字符)
- `generate_admin_password() -> str`:12 位随机密码
- `ensure_env_file(env_path, env_example_path) -> None`:.env 不存在则从 .env.example 复制,占位 SECRET_KEY 替换为真随机,空 INITIAL_ADMIN_PASSWORD 生成密码
- `force_local_host(env_path) -> None`:强制 API_HOST=127.0.0.1
- `set_cache_env_vars(project_root) -> None`:设置 PADDLE_PDX_CACHE_HOME/HF_HOME + 创建目录
- `update_env_value(env_path, key, value) -> None`:更新 .env 中某个 key
- 测试:11 个用例覆盖所有函数

### 批次 2:opencli_checker + ocr_installer

**opencli_checker.py**:
- `OPENCLI_DOWNLOAD_URL = "https://opencli.info/download"`
- `OpenCLIResult` dataclass:ok/version/reason/message
- `check_opencli(bin_path="opencli", timeout=10.0) -> OpenCLIResult`:调用 `opencli doctor`,根据返回码和输出分类(not_installed/daemon_not_running/extension_not_connected/timeout/unknown_error)
- 测试:7 个用例(成功/未安装/daemon 未运行/扩展未连/超时/未知错误/下载 URL)

**ocr_installer.py**:
- `get_addon_url(os_name, arch, version) -> str`:构建 GitHub Release 下载 URL
- `get_ocr_status(project_root) -> dict`:检测安装状态(not_installed/installing/installed + version)
- `download_and_install(project_root, os_name, arch, version, venv_python, ...) -> OcrInstallResult`:下载→校验 SHA256→解压→pip 装 wheels→复制模型→写版本文件
- 辅助函数:`_get_disk_free_bytes`/`_download_file`/`_sha256`/`_extract_zip`/`_pip_install_wheels`
- 测试:8 个用例(URL 生成/状态检测/安装成功/磁盘不足/SHA256 失败回滚)

### 批次 3:process_manager

**process_manager.py**:
- `ProcessManager` 类:管理 api/worker/beat 三个子进程
- `start_service(name)/stop_service(name, timeout)/restart_service(name)/stop_all()/get_status()/get_logs_tail(lines)/cleanup()`
- 子进程 stdout/stderr 写到 `data/logs/{name}.log`
- 默认命令:uvicorn/celery worker/celery beat
- 测试:5 个用例(初始状态/启动/停止全部/重启/日志写入/进程退出检测)

### 批次 4:status_server + main.py

**status_server.py**:
- FastAPI 应用,提供状态接口:
  - `GET /status`:三服务状态 + 端口 + 版本
  - `POST /service/{name}/restart`:重启服务
  - `POST /service/all/stop`:停止全部
  - `GET /opencli/test`:测试 OpenCLI
  - `GET /opencli/download-url`:返回下载 URL
  - `GET /ocr/status`:OCR 安装状态
  - `POST /ocr/install`:触发下载安装(异步)
  - `GET /ocr/install-progress`:查询进度
  - `POST /ocr/test`:测试 OCR(调后端 /api/v1/diagnostics/ocr)
  - `GET /logs/tail?lines=50`:获取最近日志
- 测试:各接口的 happy path + error case

**main.py**:
- PyWebView 启动入口
- 启动流程:加载 .env → set_cache_env_vars → 找可用端口 → 启动状态服务 → 启动三服务子进程 → 打开 PyWebView 窗口
- 窗口关闭时 cleanup

---

## Self-Review

**1. Spec coverage:**
- § 2.1 进程模型 → process_manager ✓
- § 2.2 启动顺序 → main.py ✓
- § 2.4 端口探测 → port_finder ✓
- § 2.5 OpenCLI 测试 → opencli_checker ✓
- § 2.6 OCR 测试 → status_server 的 /ocr/test 调后端接口 ✓
- § 5 OCR 安装 → ocr_installer ✓
- § 13 安全补强 → env_bootstrap 的 force_local_host/generate_secret_key/set_cache_env_vars ✓

**2. Placeholder scan:** 测试和实现代码在子代理派遣时提供完整内容。

**3. Type consistency:**
- `OpenCLIResult` dataclass 字段在 opencli_checker 和 status_server 一致
- `OcrInstallResult` dataclass 字段在 ocr_installer 和 status_server 一致
- `ProcessManager` 方法名在 process_manager 和 status_server/main.py 一致
