"""本地存储路径安全测试。"""
from pathlib import Path

import pytest

from app.storage.local import LocalStorage


def test_save_rejects_parent_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello")

    with pytest.raises(ValueError):
        storage.save(src, "../escaped.txt")
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_save_rejects_absolute_key(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    src = tmp_path / "src.txt"
    src.write_bytes(b"hello")

    with pytest.raises(ValueError):
        storage.save(src, "/etc/passwd")


def test_save_normalizes_relative_key_under_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    src = tmp_path / "src.png"
    src.write_bytes(b"abc")

    key = storage.save(src, "nested/file.png")
    assert key == "nested/file.png"
    assert (tmp_path / "nested" / "file.png").read_bytes() == b"abc"


def test_read_rejects_parent_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.read("../../something")


def test_read_returns_bytes_for_valid_key(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    src = tmp_path / "src.bin"
    src.write_bytes(b"\x00\x01")

    saved = storage.save(src, "nested/blob.bin")
    assert storage.read(saved) == b"\x00\x01"
