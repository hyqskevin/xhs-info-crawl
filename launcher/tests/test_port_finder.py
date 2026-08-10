"""端口探测测试。"""
import socket
import pytest
from launcher.port_finder import find_available_port


def test_find_available_port_returns_first_free_port():
    """默认从起始端口开始找,返回第一个可用端口(用高位端口避免和运行中的服务冲突)。"""
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock1.bind(("127.0.0.1", 18500))
    sock1.listen()
    try:
        port = find_available_port(start=18500, end=18510)
        assert port == 18501
    finally:
        sock1.close()


def test_find_available_port_skips_occupied():
    """跳过被占用的端口。"""
    sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock1.bind(("127.0.0.1", 9000))
    sock1.listen()
    sock2.bind(("127.0.0.1", 9001))
    sock2.listen()
    try:
        port = find_available_port(start=9000, end=9010)
        assert port == 9002
    finally:
        sock1.close()
        sock2.close()


def test_find_available_port_raises_when_all_occupied():
    """所有端口都被占用时抛 RuntimeError。"""
    socks = []
    try:
        for p in range(9100, 9103):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", p))
            s.listen()
            socks.append(s)
        with pytest.raises(RuntimeError, match="全部被占用"):
            find_available_port(start=9100, end=9102)
    finally:
        for s in socks:
            s.close()


def test_find_available_port_returns_start_when_free():
    """起始端口可用时直接返回。"""
    port = find_available_port(start=9200, end=9210)
    assert port == 9200
