from pathlib import Path

import pytest

from app.storage.local import LocalStorage


def test_local_storage_saves_and_reads_by_relative_key(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image-bytes")
    storage = LocalStorage(tmp_path / "objects")

    key = storage.save(source, "notes/001/image.jpg")

    assert key == "notes/001/image.jpg"
    assert storage.read(key) == b"image-bytes"


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image-bytes")
    storage = LocalStorage(tmp_path / "objects")

    with pytest.raises(ValueError, match="Invalid storage key"):
        storage.save(source, "../outside.jpg")
