# 所有写操作限制在项目内 — 设计

**日期**: 2026-08-10
**关联**: 用户反馈"整个项目写操作，下载的文件操作应该都只能放在项目内，不能污染项目外部文件目录"

## 1. 背景

排查发现项目存在 6 处未修复的"写项目外目录"问题：

### 生产代码（2 处）
1. `backend/app/services/task_registry.py:26` — 硬编码 `/tmp/xhs_task_registry.json`（跨进程任务注册表，API 与 worker 共享）
2. `backend/app/services/poster_renderer.py:242` — `tempfile.mkdtemp(prefix="poster-render-")` 写系统 tempdir

### 测试代码（3 处）
3. `backend/tests/test_poster_renderer.py:177,230,248,283` — `tempfile.TemporaryDirectory()` 写系统 tempdir
4. `backend/tests/test_system_config_api.py:18` — `NamedTemporaryFile(delete=False)` 不清理
5. `backend/tests/test_task_registry.py:13` + `test_adapter_popen_register.py:14` — 直接引用生产 `/tmp/xhs_task_registry.json`

### 测试脚本（1 组）
6. `tests/scripts/test_poster_*.sh` — 硬编码 `/tmp/poster-*.html`、`/tmp/multi-render.html`、`/tmp/poster_templates.json`、`/tmp/dup.json`、`/tmp/note_imgs.json`

### 文档级隐患
- `SPEC.md:814,823` + `docs/crawler-design.md:22,31` — 示例引导用户在 `$HOME/chrome-debug-profile` 创建目录

### 第三方工具间接行为（预防性重定向）
- huggingface_hub 模型缓存可能写 `~/.cache/huggingface`（paddlex 传递依赖，未显式设置 `HF_HOME`）

## 2. 设计

### 2.1 生产代码

#### 2.1.1 task_registry.py — 改为项目内路径

**当前**：
```python
REGISTRY_PATH = Path("/tmp/xhs_task_registry.json")
```

**改为**：
- `Settings` 新增字段 `task_registry_path: Path = Path("./data/run/task_registry.json")`
- `task_registry.py` 从 `get_settings().task_registry_path` 读取路径
- `ensure_runtime_directories()` 新增 `task_registry_path.parent` 创建
- 跨进程通信仍有效：API 和 worker 都读项目内同一文件

#### 2.1.2 poster_renderer.py — 改为项目内临时目录

**当前**：
```python
tmp_dir = tempfile.mkdtemp(prefix="poster-render-")
```

**改为**：
- `Settings` 新增字段 `tmp_dir: Path = Path("./data/tmp")`
- `poster_renderer.py` 在 `settings.tmp_dir / f"poster-render-{uuid4().hex[:8]}"` 下创建临时目录
- 保留 `finally: shutil.rmtree(tmp_dir)` 清理逻辑
- `ensure_runtime_directories()` 新增 `tmp_dir` 创建

### 2.2 测试代码

#### 2.2.1 test_poster_renderer.py — 改用 tmp_path fixture

**当前**：`with tempfile.TemporaryDirectory() as tmpdir:`

**改为**：用 pytest 内置 `tmp_path` fixture（自动在项目内 `data/tmp/pytest-*/` 下创建，测试结束自动清理）

#### 2.2.2 test_system_config_api.py — 改用 tmp_path

**当前**：`NamedTemporaryFile(mode="w", suffix=".env", delete=False)`

**改为**：`tmp_path / ".env"`（tmp_path fixture 自动清理）

#### 2.2.3 test_task_registry.py / test_adapter_popen_register.py — 改用项目内路径

**当前**：`REGISTRY = Path("/tmp/xhs_task_registry.json")`

**改为**：通过 `monkeypatch` 修改 `task_registry.REGISTRY_PATH` 指向 `tmp_path / "task_registry.json"`，不污染生产路径

### 2.3 测试脚本

#### 2.3.1 tests/scripts/test_poster_*.sh — 改用项目内 data/tmp/

**当前**：`TMP_HTML="/tmp/poster-real-render.html"` 等

**改为**：`TMP_HTML="$ROOT_DIR/data/tmp/poster-real-render.html"`，并在脚本开头 `mkdir -p "$ROOT_DIR/data/tmp"`

### 2.4 文档

#### 2.4.1 SPEC.md + crawler-design.md

**当前**：`--user-data-dir="$HOME/chrome-debug-profile"`

**改为**：删除该示例说明，改为"opencli 自管理浏览器 session（CDP 模式连已存在浏览器，daemon+扩展模式用扩展接管），项目代码不传 `--user-data-dir`"

### 2.5 第三方工具预防性重定向

#### 2.5.1 dev-worker.sh 添加 HF_HOME

```bash
export HF_HOME="$ROOT_DIR/data/huggingface"
```

预防 huggingface_hub 在 paddlex 内部下载时写 `~/.cache/huggingface`

## 3. 不修改的部分

以下属于第三方工具自身行为，项目代码无法控制，不修改：
- opencli 自身的 `~/.opencli` / `~/.config/opencli`（项目只 exec 二进制）
- Chrome 用户数据目录 `~/Library/Application Support/Google/Chrome/`（Chrome 运行时行为）
- Playwright 浏览器二进制 `~/Library/Caches/ms-playwright/`（`playwright install` 时行为）
- uv / npm 包管理器缓存（`~/.cache/uv`、`~/.npm`）

## 4. 验收

- [ ] 生产代码无 `/tmp/`、`tempfile.gettempdir()`、`Path.home()`、`expanduser('~')` 硬编码
- [ ] 测试代码无 `/tmp/` 硬编码，用 `tmp_path` fixture
- [ ] 测试脚本无 `/tmp/` 硬编码，用项目内 `data/tmp/`
- [ ] 文档无 `$HOME/chrome-debug-profile` 示例
- [ ] dev-worker.sh 设置 `HF_HOME` 重定向
- [ ] task_registry 路径可配置（通过 Settings）
- [ ] poster_renderer 临时目录可配置（通过 Settings）
- [ ] 后端全量测试通过
- [ ] 新增测试：验证 task_registry 路径在项目内、poster_renderer 临时目录在项目内

## 5. 测试计划

### 单元测试（先红后绿）

1. `test_task_registry_path_is_in_project` — 验证 `REGISTRY_PATH` 在 `project_root/data/` 下
2. `test_poster_renderer_tmp_dir_is_in_project` — 验证 poster_renderer 创建的临时目录在 `project_root/data/tmp/` 下
3. `test_settings_has_tmp_dir_field` — 验证 Settings 有 `tmp_dir` 字段且默认 `./data/tmp`
4. `test_settings_has_task_registry_path_field` — 验证 Settings 有 `task_registry_path` 字段且默认 `./data/run/task_registry.json`

### 静态检查

5. `test_no_hardcoded_tmp_path_in_production_code` — grep 生产代码无 `/tmp/`、`tempfile.gettempdir()`、`Path.home()`、`expanduser('~')`
