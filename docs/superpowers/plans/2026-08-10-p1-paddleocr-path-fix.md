# P1 PaddleOCR 路径修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 废弃死配置 `paddleocr_model_dir`,在 Python 代码里设置 `PADDLE_PDX_CACHE_HOME` 和 `HF_HOME` 环境变量,确保 paddleocr 不污染用户 home 目录。

**Architecture:** 在 `Settings` 类新增 `paddle_pdx_cache_home` 和 `huggingface_cache_home` 字段(替代死配置);在 `get_settings()` 里 `os.environ.setdefault` 两个变量,让任何入口(uvicorn/celery/pytest)都生效;清理 `.env.example`、`conftest.py`、`test_scaffold_contract.py`、`docs/paddleocr-setup.md` 里的死配置引用。

**Tech Stack:** Python 3.11 + pydantic-settings + pytest

**Spec:** `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md` § 7.3

---

### Task 1: 写失败测试 — Settings 字段变更

**Files:**
- Modify: `backend/tests/test_config.py`（已存在,新增用例）

- [ ] **Step 1: 查看现有 test_config.py 末尾**

Run: `cd backend && tail -20 tests/test_config.py`

确认文件末尾位置,便于追加新用例。

- [ ] **Step 2: 追加失败测试**

在 `backend/tests/test_config.py` 末尾追加:

```python
def test_paddleocr_model_dir_field_removed() -> None:
    """死配置 paddleocr_model_dir 已删除(从未被 paddleocr_adapter 使用)。"""
    settings = Settings(_env_file=None)
    assert not hasattr(settings, "paddleocr_model_dir"), (
        "paddleocr_model_dir 是死配置,paddleocr_adapter.py 从未使用,应已删除"
    )


def test_paddle_pdx_cache_home_field_exists_with_default() -> None:
    """新增 paddle_pdx_cache_home 字段,默认 ./data/paddlex。"""
    settings = Settings(_env_file=None)
    assert hasattr(settings, "paddle_pdx_cache_home")
    assert settings.paddle_pdx_cache_home == Path("./data/paddlex")


def test_huggingface_cache_home_field_exists_with_default() -> None:
    """新增 huggingface_cache_home 字段,默认 ./data/huggingface。"""
    settings = Settings(_env_file=None)
    assert hasattr(settings, "huggingface_cache_home")
    assert settings.huggingface_cache_home == Path("./data/huggingface")


def test_paddle_pdx_cache_home_reads_from_env() -> None:
    """PADDLE_PDX_CACHE_HOME 环境变量可覆盖默认值。"""
    settings = Settings(_env_file=None, _env_file_encoding="utf-8")
    # 通过 pydantic-settings 的 validation_alias 读取
    import os
    old = os.environ.get("PADDLE_PDX_CACHE_HOME")
    try:
        os.environ["PADDLE_PDX_CACHE_HOME"] = "/tmp/test-paddlex"
        settings2 = Settings(_env_file=None)
        assert settings2.paddle_pdx_cache_home == Path("/tmp/test-paddlex")
    finally:
        if old is None:
            os.environ.pop("PADDLE_PDX_CACHE_HOME", None)
        else:
            os.environ["PADDLE_PDX_CACHE_HOME"] = old
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && pytest tests/test_config.py::test_paddleocr_model_dir_field_removed tests/test_config.py::test_paddle_pdx_cache_home_field_exists_with_default tests/test_config.py::test_huggingface_cache_home_field_exists_with_default -v`

Expected: 3 个用例 FAIL
- `test_paddleocr_model_dir_field_removed` 失败:字段仍存在
- `test_paddle_pdx_cache_home_field_exists_with_default` 失败:字段不存在
- `test_huggingface_cache_home_field_exists_with_default` 失败:字段不存在

---

### Task 2: 修改 Settings — 删除死配置 + 新增两个字段

**Files:**
- Modify: `backend/app/core/config.py:60`（删除 `paddleocr_model_dir`）
- Modify: `backend/app/core/config.py`（在 `paddleocr_model_dir` 原位置新增两个字段）

- [ ] **Step 1: 删除 paddleocr_model_dir 字段**

在 `backend/app/core/config.py:60` 删除:

```python
    paddleocr_model_dir: Path = Path("./data/models/paddleocr")
```

- [ ] **Step 2: 在原位置新增两个字段**

在 `backend/app/core/config.py` 删除位置新增（与 `tmp_dir_setting` 等字段同区域,使用 `Field` + `validation_alias`）:

```python
    # PaddleOCR 3.x 模型缓存目录（通过环境变量 PADDLE_PDX_CACHE_HOME 生效）
    paddle_pdx_cache_home: Path = Field(
        Path("./data/paddlex"),
        validation_alias="PADDLE_PDX_CACHE_HOME",
    )
    # HuggingFace 缓存目录（paddlex 传递依赖，通过环境变量 HF_HOME 生效）
    huggingface_cache_home: Path = Field(
        Path("./data/huggingface"),
        validation_alias="HF_HOME",
    )
```

- [ ] **Step 3: 在 ensure_runtime_directories 方法里加入新目录**

在 `backend/app/core/config.py` 的 `ensure_runtime_directories` 方法里,在 `self.tmp_dir,` 后面追加:

```python
        self.tmp_dir,
        self.paddle_pdx_cache_home,
        self.huggingface_cache_home,
```

- [ ] **Step 4: 运行 Task 1 的测试确认通过**

Run: `cd backend && pytest tests/test_config.py::test_paddleocr_model_dir_field_removed tests/test_config.py::test_paddle_pdx_cache_home_field_exists_with_default tests/test_config.py::test_huggingface_cache_home_field_exists_with_default tests/test_config.py::test_paddle_pdx_cache_home_reads_from_env -v`

Expected: 4 个用例 PASS

---

### Task 3: 写失败测试 — get_settings 设置环境变量

**Files:**
- Create: `backend/tests/test_paddleocr_cache_env.py`

- [ ] **Step 1: 写测试文件**

创建 `backend/tests/test_paddleocr_cache_env.py`:

```python
"""验证 get_settings() 调用后,环境变量 PADDLE_PDX_CACHE_HOME 和 HF_HOME 已设置。

之前只靠 scripts/dev-worker.sh 的 export,直接跑 uvicorn/celery 时会缺失,
导致 paddleocr 污染 ~/.paddlex/（违反 AGENTS.md 硬约束）。
"""
import os
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings, get_settings


def test_get_settings_sets_paddle_pdx_cache_home_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 后 os.environ['PADDLE_PDX_CACHE_HOME'] 已设置。"""
    # 清除 lru_cache 和环境变量
    get_settings.cache_clear()
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "paddlex"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))

    get_settings.cache_clear()
    settings = get_settings()

    assert os.environ.get("PADDLE_PDX_CACHE_HOME") is not None
    assert str(settings.paddle_pdx_cache_home.resolve()) == os.environ["PADDLE_PDX_CACHE_HOME"]


def test_get_settings_sets_hf_home_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 后 os.environ['HF_HOME'] 已设置。"""
    get_settings.cache_clear()
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(tmp_path / "paddlex"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "huggingface"))

    get_settings.cache_clear()
    settings = get_settings()

    assert os.environ.get("HF_HOME") is not None
    assert str(settings.huggingface_cache_home.resolve()) == os.environ["HF_HOME"]


def test_get_settings_creates_cache_directories(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 创建缓存目录(若不存在)。"""
    get_settings.cache_clear()
    paddlex_dir = tmp_path / "paddlex"
    hf_dir = tmp_path / "huggingface"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(paddlex_dir))
    monkeypatch.setenv("HF_HOME", str(hf_dir))

    get_settings.cache_clear()
    get_settings()

    assert paddlex_dir.is_dir()
    assert hf_dir.is_dir()


def test_get_settings_does_not_override_existing_env(tmp_path: Path, monkeypatch) -> None:
    """get_settings() 用 setdefault,不覆盖已存在的环境变量。"""
    get_settings.cache_clear()
    pre_existing = str(tmp_path / "pre-existing-paddlex")
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", pre_existing)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "pre-existing-hf"))

    get_settings.cache_clear()
    get_settings()

    # 环境变量保持用户预设值,不被 settings 默认值覆盖
    assert os.environ["PADDLE_PDX_CACHE_HOME"] == pre_existing
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_paddleocr_cache_env.py -v`

Expected: 4 个用例 FAIL（`get_settings` 还没设置环境变量）

---

### Task 4: 修改 get_settings — 设置环境变量

**Files:**
- Modify: `backend/app/core/config.py`（`get_settings` 函数）

- [ ] **Step 1: 修改 get_settings 函数**

在 `backend/app/core/config.py` 末尾的 `get_settings` 函数,改为:

```python
import os


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # 关键:在 Python 进程启动时设置环境变量,确保 paddleocr/huggingface 不污染用户 home
    # 之前只靠 scripts/dev-worker.sh 的 export,直接跑 uvicorn/celery 时会缺失
    cache_home = str(settings.paddle_pdx_cache_home.resolve())
    hf_home = str(settings.huggingface_cache_home.resolve())
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", cache_home)
    os.environ.setdefault("HF_HOME", hf_home)
    # 确保目录存在
    settings.paddle_pdx_cache_home.mkdir(parents=True, exist_ok=True)
    settings.huggingface_cache_home.mkdir(parents=True, exist_ok=True)
    return settings
```

注意:`import os` 应在文件顶部,如果已有就不用重复加。

- [ ] **Step 2: 运行测试确认通过**

Run: `cd backend && pytest tests/test_paddleocr_cache_env.py -v`

Expected: 4 个用例 PASS

---

### Task 5: 更新 .env.example — 替换 PADDLEOCR_MODEL_DIR

**Files:**
- Modify: `.env.example:82-83`

- [ ] **Step 1: 替换 .env.example 中的 PADDLEOCR_MODEL_DIR**

在 `.env.example:82-83` 把:

```env
# PADDLEOCR_MODEL_DIR：PaddleOCR 模型文件保存目录。
PADDLEOCR_MODEL_DIR=./data/models/paddleocr
```

替换为:

```env
# PADDLE_PDX_CACHE_HOME：PaddleOCR 3.x 模型缓存目录（paddleocr 通过此环境变量决定模型下载/加载位置）。
# Settings 启动时自动 setdefault,无需手动设置;此变量供 scripts/dev-worker.sh 和打包版启动器使用。
PADDLE_PDX_CACHE_HOME=./data/paddlex

# HF_HOME：HuggingFace 缓存目录（paddlex 传递依赖,预防写 ~/.cache/huggingface）。
HF_HOME=./data/huggingface
```

- [ ] **Step 2: 运行 test_scaffold_contract 确认它会失败（因为还引用旧 key）**

Run: `cd backend && pytest tests/test_scaffold_contract.py::test_environment_example_contains_phase_one_settings -v`

Expected: FAIL（测试还在断言 `PADDLEOCR_MODEL_DIR=./data/models/paddleocr` 存在）

---

### Task 6: 更新 test_scaffold_contract.py — 移除旧 key,加新 key

**Files:**
- Modify: `backend/tests/test_scaffold_contract.py:51`

- [ ] **Step 1: 替换 PADDLEOCR_MODEL_DIR 引用**

在 `backend/tests/test_scaffold_contract.py:51` 把:

```python
        "PADDLEOCR_MODEL_DIR=./data/models/paddleocr",
```

替换为:

```python
        "PADDLE_PDX_CACHE_HOME=./data/paddlex",
        "HF_HOME=./data/huggingface",
```

- [ ] **Step 2: 运行测试确认通过**

Run: `cd backend && pytest tests/test_scaffold_contract.py -v`

Expected: PASS

---

### Task 7: 更新 conftest.py — 移除 PADDLEOCR_MODEL_DIR,加新 key

**Files:**
- Modify: `backend/tests/conftest.py:65`

- [ ] **Step 1: 替换 PADDLEOCR_MODEL_DIR 引用**

在 `backend/tests/conftest.py:65` 把:

```python
    "PADDLEOCR_MODEL_DIR",
```

替换为:

```python
    "PADDLE_PDX_CACHE_HOME",
    "HF_HOME",
```

- [ ] **Step 2: 运行 conftest 加载验证**

Run: `cd backend && pytest tests/test_config.py tests/test_paddleocr_cache_env.py tests/test_scaffold_contract.py -v`

Expected: 全部 PASS

---

### Task 8: 更新 docs/paddleocr-setup.md

**Files:**
- Modify: `docs/paddleocr-setup.md:64`

- [ ] **Step 1: 替换 .env 配置示例**

在 `docs/paddleocr-setup.md:64` 把:

```bash
PADDLEOCR_MODEL_DIR=./data/models/paddleocr
```

替换为:

```bash
# paddleocr 3.x 通过环境变量决定模型缓存位置（Settings 启动时自动 setdefault）
PADDLE_PDX_CACHE_HOME=./data/paddlex
HF_HOME=./data/huggingface
```

并在下面的说明文字里,把"模型目录位于 `data/`,不会提交到 Git。首次运行会下载模型,需要网络。"改为:

"模型缓存目录 `data/paddlex/official_models/` 不会提交到 Git。首次运行会下载模型,需要网络。`PADDLE_PDX_CACHE_HOME` 由 `get_settings()` 在进程启动时设置,无需手动 export(之前只靠 `scripts/dev-worker.sh` 的 export,直接跑 uvicorn/celery 会缺失)。"

- [ ] **Step 2: 验证文档可读**

Run: `cd /Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl && head -80 docs/paddleocr-setup.md`

Expected: 看到 `PADDLE_PDX_CACHE_HOME=./data/paddlex` 而非 `PADDLEOCR_MODEL_DIR`

---

### Task 9: 全量测试 + 静态扫描验证

**Files:**
- 无修改,仅验证

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && pytest -q`

Expected: 全部 PASS,无 FAIL。如果有用例因 `paddleocr_model_dir` 引用失败,检查是否漏改。

- [ ] **Step 2: 项目内写操作静态扫描**

Run: `cd backend && pytest tests/test_project_internal_writes.py -v`

Expected: PASS（确认无新增外部路径引用）

- [ ] **Step 3: grep 确认无残留死配置引用**

Run: `cd /Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl && grep -rn "paddleocr_model_dir\|PADDLEOCR_MODEL_DIR" --include="*.py" --include="*.md" --include="*.example" --include="*.sh" .`

Expected: 无输出（或仅在 docs/superpowers/specs/ 里的历史 spec 引用,可忽略）

如果还有残留,逐一清理。

---

### Task 10: 提交

**Files:**
- 无

- [ ] **Step 1: git status 检查改动文件**

Run: `cd /Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl && git status`

Expected 改动文件:
- `backend/app/core/config.py`
- `backend/tests/conftest.py`
- `backend/tests/test_config.py`
- `backend/tests/test_paddleocr_cache_env.py`（新增）
- `backend/tests/test_scaffold_contract.py`
- `.env.example`
- `docs/paddleocr-setup.md`
- `docs/TODO.md`（新增 P1 TODO 项）
- `docs/superpowers/specs/2026-08-10-one-click-packaging-design.md`（spec）
- `docs/superpowers/plans/2026-08-10-p1-paddleocr-path-fix.md`（本 plan）

- [ ] **Step 2: git add + commit**

```bash
cd /Users/hanamaki_mac_mini/Documents/github/project/xhs-info-crawl
git add backend/app/core/config.py backend/tests/conftest.py backend/tests/test_config.py backend/tests/test_paddleocr_cache_env.py backend/tests/test_scaffold_contract.py .env.example docs/paddleocr-setup.md docs/TODO.md docs/superpowers/specs/2026-08-10-one-click-packaging-design.md docs/superpowers/plans/2026-08-10-p1-paddleocr-path-fix.md
git commit -m "$(cat <<'EOF'
fix(config): 废弃 paddleocr_model_dir 死配置 + Python 代码设置 PADDLE_PDX_CACHE_HOME/HF_HOME

之前 paddleocr_model_dir 从未被 paddleocr_adapter.py 使用(死配置);
PADDLE_PDX_CACHE_HOME/HF_HOME 只在 scripts/dev-worker.sh 里 export,
直接跑 uvicorn/celery 会污染 ~/.paddlex/(违反 AGENTS.md 硬约束)。

修复:Settings 新增 paddle_pdx_cache_home/huggingface_cache_home 字段;
get_settings() 用 os.environ.setdefault 设置两个变量;
.env.example/test_scaffold_contract/conftest/paddleocr-setup.md 同步更新。

关联 TODO: docs/TODO.md P1 路径修复
关联 spec: docs/superpowers/specs/2026-08-10-one-click-packaging-design.md § 7.3
EOF
)"
```

- [ ] **Step 3: 验证提交成功**

Run: `git log -1 --oneline`

Expected: 看到 commit 信息

---

### Task 11: 提示用户重启 worker

**Files:**
- 无

- [ ] **Step 1: 提示用户**

向用户输出:

```
P1 路径修复已完成并提交。

⚠️ 需要重启 celery worker 和 beat:
- 修改了 backend/app/core/config.py(Settings 字段变更)
- 修改了 backend/tests/conftest.py(测试 fixture)

请执行:
  pkill -f "celery" && scripts/dev-worker.sh &
  pkill -f "celery beat" && scripts/dev-beat.sh &

(或用你常用的重启方式)

重启后,worker 启动时 get_settings() 会自动设置 PADDLE_PDX_CACHE_HOME 和 HF_HOME,
paddleocr 不再污染 ~/.paddlex/。
```

---

## Self-Review

**1. Spec coverage:** 
- § 7.3 步骤 1(废弃死配置)→ Task 2 + Task 5 + Task 6 + Task 7 + Task 8 ✓
- § 7.3 步骤 2(Python 代码设置环境变量)→ Task 4 ✓
- § 7.3 步骤 3(新增配置字段)→ Task 2 ✓
- § 7.3 步骤 4(更新 .env.example)→ Task 5 ✓
- § 7.3 步骤 5(paddleocr_adapter.py 不需要改)→ 已确认 ✓
- § 7.3 测试要求 → Task 1 + Task 3 + Task 6 + Task 7 + Task 9 ✓

**2. Placeholder scan:** 无 TBD/TODO,所有代码块完整。

**3. Type consistency:** 
- `paddle_pdx_cache_home` 和 `huggingface_cache_home` 字段名在 Task 2/3/4 一致
- `PADDLE_PDX_CACHE_HOME` 和 `HF_HOME` 环境变量名在所有 Task 一致
- `Path("./data/paddlex")` 和 `Path("./data/huggingface")` 默认值在所有 Task 一致
