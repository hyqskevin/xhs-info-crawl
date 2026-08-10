"""验证 dev-*.sh 启动脚本不 source 全部 .env。

关联 spec: docs/superpowers/specs/2026-08-10-dev-scripts-no-source-env-design.md

根因：dev-*.sh 用 `set -a; source .env; set +a` 把 .env 全量注入 os.environ，
pydantic_settings 优先级 os.environ > .env，导致配置中心改 .env 后，
uvicorn --reload 重启子进程从父进程继承旧 os.environ，Settings 读到旧值。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"

DEV_SCRIPTS = ["dev-api.sh", "dev-worker.sh", "dev-beat.sh", "dev-web.sh"]


def test_dev_scripts_exist() -> None:
    """三个 dev 脚本都存在。"""
    for name in DEV_SCRIPTS:
        assert (SCRIPTS_DIR / name).exists(), f"{name} 不存在"


def test_dev_scripts_do_not_source_env_file() -> None:
    """dev-*.sh 不应 `set -a; source .env`，避免 os.environ 污染 pydantic_settings。

    脚本只能用 grep 从 .env 读取启动参数（API_HOST/CELERY_*），不能全量 source。
    """
    for name in DEV_SCRIPTS:
        script = SCRIPTS_DIR / name
        content = script.read_text(encoding="utf-8")
        # 不应出现 set -a（自动 export source 的变量）
        assert "set -a" not in content, (
            f"{name} 不应使用 `set -a`：会把 source 的变量全量注入 os.environ，"
            "导致 pydantic_settings 的 os.environ 优先级覆盖 .env 文件新值"
        )
        # exec 之前的部分不应 source .env
        before_exec = content.split("exec ")[0] if "exec " in content else content
        assert not re.search(r"^\s*source\s+.*\.env", before_exec, re.MULTILINE), (
            f"{name} 不应 `source .env`：应改为 grep 读取启动参数"
        )


def test_dev_scripts_use_grep_for_startup_params() -> None:
    """dev-*.sh 应使用 grep 从 .env 读取启动参数，而非 source。"""
    for name in DEV_SCRIPTS:
        script = SCRIPTS_DIR / name
        content = script.read_text(encoding="utf-8")
        assert "grep" in content, f"{name} 应使用 grep 从 .env 读取启动参数"
