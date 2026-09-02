"""launcher/ports.py 端口常量模块测试。

P2-6 修复:5173 / 8000 / 8001 / 9000 等端口数字散落在 6 个 launcher 文件
(env_bootstrap / main / process_manager / status_server / inject_app_config /
port_finder 默认值),修改端口时易遗漏;且 .env 文档(API_PORT=8000)与代码
默认值不一致排查困难。

抽出动机:
- launcher/ports.py 单一来源
- 端口范围(WEB_PORT 5173-5199 / API_PORT 8001-8020 / STATUS_PORT 9000-9019)
  也集中导出

TDD:
- RED:断言 launcher.ports 模块导出预期常量(目前不存在 → import 失败)
- GREEN:创建 launcher/ports.py + 替换 6 文件魔法数字
"""
import pytest


def test_ports_module_importable() -> None:
    """launcher.ports 模块可导入。"""
    import launcher.ports  # noqa: F401


@pytest.mark.parametrize(
    "attr,expected",
    [
        # 默认端口
        ("WEB_PORT_DEFAULT", 5173),
        ("API_PORT_DEFAULT", 8000),
        ("API_PORT_SCAN_START", 8001),
        ("STATUS_PORT_SCAN_START", 9000),
        # 端口扫描范围 (start, end)
        # 用 tuple 校验,确保 start < end
    ],
)
def test_ports_module_exposes_expected_int_constants(attr: str, expected: int) -> None:
    """launcher.ports 暴露预期 int 常量。"""
    from launcher import ports

    assert hasattr(ports, attr), f"launcher.ports.{attr} 应存在(消除 {expected} 魔法数字)"
    assert getattr(ports, attr) == expected


@pytest.mark.parametrize(
    "range_attr,start,end",
    [
        ("WEB_PORT_SCAN_RANGE", 5173, 5199),
        ("API_PORT_SCAN_RANGE", 8001, 8020),
        ("STATUS_PORT_SCAN_RANGE", 9000, 9019),
    ],
)
def test_ports_module_exposes_scan_ranges(range_attr: str, start: int, end: int) -> None:
    """端口扫描范围以 tuple 形式导出(start, end)。"""
    from launcher import ports

    assert hasattr(ports, range_attr), f"launcher.ports.{range_attr} 应存在"
    value = getattr(ports, range_attr)
    assert isinstance(value, tuple) and len(value) == 2
    assert value == (start, end), f"{range_attr} 应为 ({start}, {end}),实际 {value}"