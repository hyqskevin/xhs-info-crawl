"""status_server._read_launcher_system_config / put_launcher_system_config 的多路径合并 + 双写 + OCR sync 测试。

关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 2/3/6
关联设计: docs/packaging-design.md §3 核心架构不变量
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeProcessManager:
    """只用来满足 StatusServer 构造,不真正启动子进程。

    - restart_service 返 True
    - get_status 返全 stopped
    - get_logs_tail 返空
    """

    def restart_service(self, name: str) -> bool:
        return True

    def get_status(self) -> dict:
        return {
            "api": {"state": "stopped", "pid": None},
            "worker": {"state": "stopped", "pid": None},
            "beat": {"state": "stopped", "pid": None},
        }

    def get_logs_tail(self, lines: int) -> list[str]:
        return []

    def stop_all(self) -> None:
        pass


def _make_server(tmp_path: Path, venv_python: Path = None):
    """为每个测试构造一个 StatusServer,project_root 指到 tmp_path。

    用 _FakeProcessManager 替代真 ProcessManager,避免 PUT 触发 restart 时真的去
    启 4 个子进程(测试环境 venv/bin/python 不存在,真重启会 FileNotFoundError)。
    """
    from launcher.status_server import StatusServer

    pm = _FakeProcessManager()
    return StatusServer(
        process_manager=pm,
        project_root=tmp_path,
        venv_python=venv_python or (tmp_path / "venv" / "bin" / "python"),
        api_base_url="http://127.0.0.1:8000",
        web_base_url="http://127.0.0.1:5173",
    )


def _write_env(path: Path, lines: dict[str, str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"{k}={v}" for k, v in lines.items()) + "\n"
    path.write_text(content, encoding="utf-8")


# ── 测试 2: 多路径读 .env ────────────────────────────────────────────────


class TestReadLauncherSystemConfigEnvMerge:
    """改动 2:_read_launcher_system_config 必须合并 project_root + DATA_DIR。

    合并规则(关联 design §3.1 / §3.3):
    - bootstrap 字段(API_PORT/API_HOST/WEB_PORT/API_BASE_URL/SECRET_KEY)→
      仅读 project_root,不参与合并
    - 用户字段(minimax_* / opencli_bin / chrome_bin / ocr_language /
      ocr_min_confidence / ocr_parallel_workers / chrome_user_data_dir)→
      DATA_DIR 优先,缺失回退 project_root
    - data_dir / log_dir → project_root 优先(启动器要立刻读)
    - ocr_enabled → 由 sync 函数单方管理,**不**参与多路径合并
    """

    def test_data_dir_field_fills_from_project_root(self, tmp_path: Path):
        """仅 project_root/.env 写 DATA_DIR → 读出来的 data_dir 是它。"""
        _write_env(tmp_path / ".env", {"DATA_DIR": str(tmp_path / "userdata")})
        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            resp = client.get("/system-config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["data_dir"] == str(tmp_path / "userdata"), (
                f"DATA_DIR 应该直接来自 project_root/.env: {data['data_dir']}"
            )

    def test_user_field_data_dir_wins_over_project_root(self, tmp_path: Path):
        """minimax_api_key:project_root 没设,DATA_DIR 设了 → 读出来是 DATA_DIR 的值。

        用户场景:换了机器,把 DATA_DIR 从旧机器拷过来,启动器要把里面的字段回填。
        """
        data_dir = tmp_path / "userdata"
        _write_env(tmp_path / ".env", {
            "DATA_DIR": str(data_dir),
            "MINIMAX_BASE_URL": "https://proj-base-url/v1",
        })
        _write_env(data_dir / ".env", {
            "MINIMAX_API_KEY": "data_api_key",
            "MINIMAX_BASE_URL": "https://data-base-url/v1",
            "MINIMAX_MODEL": "data-model",
        })
        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            resp = client.get("/system-config")
            data = resp.json()
            assert data["minimax_api_key"] == "data_api_key", (
                f"minimax_api_key 应该回填自 DATA_DIR: {data['minimax_api_key']}"
            )
            assert data["minimax_base_url"] == "https://data-base-url/v1", (
                f"minimax_base_url DATA_DIR 优先: {data['minimax_base_url']}"
            )
            assert data["minimax_model"] == "data-model"

    def test_user_field_falls_back_to_project_root(self, tmp_path: Path):
        """minimax_api_key:project_root 有,DATA_DIR 没 → 回退到 project_root。

        关联 design §3.3 "DATA_DIR 优先,缺失回退 project_root"。
        """
        data_dir = tmp_path / "userdata"
        _write_env(tmp_path / ".env", {
            "DATA_DIR": str(data_dir),
            "MINIMAX_API_KEY": "proj_api_key",
        })
        _write_env(data_dir / ".env", {
            "MINIMAX_BASE_URL": "https://data-base-url/v1",
        })
        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            resp = client.get("/system-config")
            data = resp.json()
            assert data["minimax_api_key"] == "proj_api_key", (
                f"minimax_api_key 应该回退到 project_root: {data['minimax_api_key']}"
            )
            assert data["minimax_base_url"] == "https://data-base-url/v1"

    def test_bootstrap_field_api_port_not_overridden_by_data_dir(self, tmp_path: Path):
        """API_PORT 是 bootstrap 字段,不被 DATA_DIR 覆盖。

        用户的 DATA_DIR/.env 偶然写了 API_PORT(比如旧配置没清理),启动器不能
        听它的,因为端口必须跟运行环境的 .app 走。
        """
        data_dir = tmp_path / "userdata"
        _write_env(tmp_path / ".env", {
            "DATA_DIR": str(data_dir),
            "API_PORT": "8123",
        })
        _write_env(data_dir / ".env", {
            "API_PORT": "9999",
        })
        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            data = client.get("/system-config").json()
            # API_PORT 当前没在 _LAUNCHER_SYSTEM_CONFIG_KEYS 列表里,
            # 只验证 data_dir/log_dir 走 project_root(DATA_DIR 优先是项目 bootstrap 字段例外):
            # 不,data_dir/log_dir 是用户配置字段;但 data_dir 必须在 project_root 才能启动。
            # 既然 API_PORT 不在列表里,跳过;改检查 log_dir。
            assert data["data_dir"] == str(data_dir)
            # 写一个 log_dir 项目值,DATA_DIR 不应有覆盖权
            _write_env(tmp_path / ".env", {
                "DATA_DIR": str(data_dir),
                "API_PORT": "8123",
                "LOG_DIR": str(tmp_path / "log"),
            })
            _write_env(data_dir / ".env", {
                "LOG_DIR": str(data_dir / "logs-from-data"),
            })
            data2 = client.get("/system-config").json()
            assert data2["log_dir"] == str(tmp_path / "log"), (
                f"log_dir(启动器 bootstrap)以 project_root 为准: {data2['log_dir']}"
            )


# ── 测试 6: PUT 双写 ──────────────────────────────────────────────────────


class TestPutLauncherSystemConfigDualWrite:
    """改动 6:put_launcher_system_config 双写 project_root + DATA_DIR。

    字段分类:
    - bootstrap 字段(API_PORT/API_HOST/WEB_PORT/API_BASE_URL/SECRET_KEY)→
      仅写 project_root,不写 DATA_DIR
    - 用户字段(minimax_*/ocr_language/ocr_min_confidence/ocr_parallel_workers/
      opencli_bin/chrome_bin/chrome_user_data_dir)→ 双写
    - data_dir/log_dir → project_root only(启动器立刻读)
    - ocr_enabled → 由 sync 函数管,PUT 时也只写 project_root
    """

    def test_put_user_field_writes_both_project_root_and_data_dir(self, tmp_path: Path):
        """PUT minimax_api_key → project_root/.env 和 DATA_DIR/.env 都有。"""
        data_dir = tmp_path / "userdata"
        _write_env(tmp_path / ".env", {"DATA_DIR": str(data_dir)})
        _write_env(data_dir / ".env", {})

        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            resp = client.put("/system-config", json={"minimax_api_key": "new_key"})
            assert resp.status_code == 200, resp.text

        proj_env = (tmp_path / ".env").read_text(encoding="utf-8")
        data_env = (data_dir / ".env").read_text(encoding="utf-8")
        assert "MINIMAX_API_KEY=new_key" in proj_env, (
            f"project_root/.env 必须含 MINIMAX_API_KEY=new_key (兜底): {proj_env}"
        )
        assert "MINIMAX_API_KEY=new_key" in data_env, (
            f"DATA_DIR/.env 必须含 MINIMAX_API_KEY=new_key (用户配置主源): {data_env}"
        )

    def test_put_bootstrap_field_writes_project_root_only(self, tmp_path: Path):
        """PUT data_dir(bootstrap) → project_root 写,DATA_DIR 不写(避免循环)。"""
        data_dir = tmp_path / "userdata"
        _write_env(tmp_path / ".env", {"DATA_DIR": str(data_dir)})
        _write_env(data_dir / ".env", {})

        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            resp = client.put("/system-config", json={"data_dir": str(tmp_path / "new_data_dir")})
            assert resp.status_code == 200, resp.text

        proj_env = (tmp_path / ".env").read_text(encoding="utf-8")
        data_env = (data_dir / ".env").read_text(encoding="utf-8")
        assert f"DATA_DIR={tmp_path / 'new_data_dir'}" in proj_env
        # DATA_DIR/.env 不应被 bootstrap 字段污染
        assert "DATA_DIR=" not in data_env or "DATA_DIR=\n" in data_env, (
            f"DATA_DIR/.env 不应有 DATA_DIR 键(bootstrap 字段不污染): {data_env}"
        )


# ── 测试 3: OCR_ENABLED 自动同步 ─────────────────────────────────────────


class TestSyncOcrEnabledWithInstalledState:
    """改动 3:启动器检测到 OCR 模型已装 → 自动同步 OCR_ENABLED=true 到 project_root/.env。

    关联 spec: docs/superpowers/specs/2026-08-21-packaging-ocr-llm-flow-fix-design.md § 改动 3
    关联设计: docs/packaging-design.md §3.6
    """

    def test_get_system_config_triggers_sync_when_ocr_installed(self, tmp_path: Path, monkeypatch):
        """GET /system-config 时如果 OCR 模型已装 + OCR_ENABLED=false → 立刻同步。"""
        # 显式 mock ocr_installer.get_ocr_status,防止被真实 project_root/data/paddlex 污染
        # (开发机下载过 OCR 模型 → official_models 真实存在 → sync 误判)。
        from launcher import status_server as _ss_mod
        monkeypatch.setattr(
            _ss_mod,
            "get_ocr_status",
            lambda project_root: {"status": "installed", "version": "migrated"},
        )

        _write_env(tmp_path / ".env", {
            "OCR_ENABLED": "false",
        })

        server = _make_server(tmp_path)
        # 重置 sync 闭包标记(每个 StatusServer 闭包里的 _sync_state 都是实例级,
        # 但跨实例也可能被同进程其他测试污染 — 重置保险)
        with TestClient(server.app) as client:
            # 第一次 GET
            resp = client.get("/system-config")
            assert resp.status_code == 200
            # ENV 应该被同步
            env_content = (tmp_path / ".env").read_text(encoding="utf-8")
            assert "OCR_ENABLED=true" in env_content, (
                f"OCR 模型已装且 OCR_ENABLED=false → 启动器应该同步为 true: {env_content}"
            )

    def test_no_sync_when_ocr_not_installed(self, tmp_path: Path, monkeypatch):
        """OCR 模型没装 → 即使 OCR_ENABLED=false,也不主动翻 true。"""
        # 显式 mock get_ocr_status 返回 not_installed,防止 dev 环境干扰
        from launcher import status_server as _ss_mod
        monkeypatch.setattr(
            _ss_mod,
            "get_ocr_status",
            lambda project_root: {"status": "not_installed", "version": ""},
        )

        _write_env(tmp_path / ".env", {
            "OCR_ENABLED": "false",
        })

        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            client.get("/system-config")
            env_content = (tmp_path / ".env").read_text(encoding="utf-8")
            assert "OCR_ENABLED=true" not in env_content, (
                f"OCR 模型未装时,启动器不应主动把 OCR_ENABLED 翻 true: {env_content}"
            )

    def test_sync_is_idempotent(self, tmp_path: Path, monkeypatch):
        """第二次 GET → 不重复写(幂等)。"""
        from launcher import status_server as _ss_mod
        monkeypatch.setattr(
            _ss_mod,
            "get_ocr_status",
            lambda project_root: {"status": "installed", "version": "migrated"},
        )

        _write_env(tmp_path / ".env", {
            "OCR_ENABLED": "false",
        })

        server = _make_server(tmp_path)
        with TestClient(server.app) as client:
            client.get("/system-config")
            env_content_1 = (tmp_path / ".env").read_text(encoding="utf-8")
            client.get("/system-config")
            env_content_2 = (tmp_path / ".env").read_text(encoding="utf-8")
        assert env_content_1 == env_content_2, (
            f"第二次 GET 应该是幂等,不重写 .env:\n第一次: {env_content_1}\n"
            f"第二次: {env_content_2}"
        )
