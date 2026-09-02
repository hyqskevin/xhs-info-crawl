"""launcher 端口常量单一来源。

历史问题:5173 / 8000 / 8001 / 9000 等数字散落在 env_bootstrap / main /
process_manager / status_server / inject_app_config / port_finder 默认值,
改端口或写文档时易遗漏,排查「.env 写的 8001 启动器却用 8000」困难。

抽出后:
- 默认端口用 *int 常量*,任何模块 import 后再无魔法数字
- 端口扫描范围用 *tuple* (start, end),find_available_port(start, end) 直接解包

CDP 端口 (9222) 仍由 Chrome 默认,launcher 不直接使用,故不在本模块。

关联 spec: docs/superpowers/specs/2026-09-02-audit-batch-3-redundant-design.md §P2-6
"""

# 单端口默认值(用作 .env 缺失时的 fallback)
WEB_PORT_DEFAULT: int = 5173
API_PORT_DEFAULT: int = 8000
# API_PORT_SCAN_START:launcher 启动时 API_PORT 已被占,从 8001 开始找下一个
# 与默认 8000 差 1 是为了让「8000 已占用」的用户能直接升级到 8001,不写 .env
API_PORT_SCAN_START: int = 8001
STATUS_PORT_SCAN_START: int = 9000

# 端口扫描范围(start, end),含端点。find_available_port 解包使用。
WEB_PORT_SCAN_RANGE: tuple[int, int] = (5173, 5199)
API_PORT_SCAN_RANGE: tuple[int, int] = (8001, 8020)
STATUS_PORT_SCAN_RANGE: tuple[int, int] = (9000, 9019)