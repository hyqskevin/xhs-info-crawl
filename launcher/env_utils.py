"""launcher 子模块共用的 .env 解析工具。

仅服务于启动器 / 启动脚本等非业务代码。后端 Settings 仍走 pydantic-settings,
不要复用本模块(语义不同:pydantic 会做类型转换 + 默认值合并 + env-prefix 处理)。

抽出动机:6 个 launcher 文件各自内联了同一份「读 .env 单 key」逻辑,
行为漂移会埋坑(谁改了 strip / 谁没读注释行 / 谁对空值返回 fallback)。
集中到这里后,行为有 TDD 保障(launcher/tests/test_env_utils.py)。
"""
from pathlib import Path


def read_env_value(env_path: Path, key: str, fallback: str = "") -> str:
    """从 .env 文件读取指定 key 的字符串值。

    规则:
    - 文件不存在 → 返回 fallback(不抛异常)
    - key 不在文件里 → 返回 fallback
    - 注释行(以 # 开头)和空行跳过
    - ``KEY=``(空值)→ 返回空字符串 ``""``,**不是** fallback
    - ``partition("=")`` 只切第一个 ``=``,value 中含 ``=`` 保留
    - 行首尾 / value 周围空格被 strip

    Args:
        env_path: .env 文件路径(可为不存在的路径)
        key: 要查找的 key 名(精确匹配,strip 后比较)
        fallback: 文件不存在或 key 不在时的返回值

    Returns:
        key 对应的字符串值,或 fallback
    """
    if not env_path.exists():
        return fallback
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return fallback