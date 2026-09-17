import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.errors import InvalidScanIdError
from app.ingest.storage import ScanStorage, new_scan_id

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
RETENTION = timedelta(hours=24)


@pytest.fixture
def storage(tmp_path: Path) -> ScanStorage:
    return ScanStorage(tmp_path / "storage")


def age_workspace(path: Path, age: timedelta) -> None:
    timestamp = (NOW - age).timestamp()
    os.utime(path, (timestamp, timestamp))


def test_new_scan_ids_are_unique_32_character_hex() -> None:
    ids = {new_scan_id() for _ in range(100)}

    assert len(ids) == 100
    assert all(len(scan_id) == 32 and int(scan_id, 16) >= 0 for scan_id in ids)


def test_create_makes_upload_source_and_scratch_directories(
    storage: ScanStorage, tmp_path: Path
) -> None:
    scan_id = new_scan_id()

    workspace = storage.create(scan_id)

    assert workspace.root == tmp_path / "storage" / scan_id
    assert workspace.upload_dir.is_dir()
    assert workspace.source_dir.is_dir()
    assert workspace.scratch_dir.is_dir()


def test_create_refuses_to_reuse_an_existing_workspace(storage: ScanStorage) -> None:
    scan_id = new_scan_id()
    storage.create(scan_id)

    with pytest.raises(FileExistsError):
        storage.create(scan_id)


@pytest.mark.parametrize(
    "scan_id",
    [
        "../../etc",
        "..",
        "A" * 32,
        "g" * 32,
        "abc",
        "a" * 32 + "/../x",
        "a" * 32 + "\n",
    ],
)
def test_rejects_ids_that_are_not_scan_ids(storage: ScanStorage, scan_id: str) -> None:
    with pytest.raises(InvalidScanIdError):
        storage.workspace(scan_id)


def test_delete_removes_workspace_and_ignores_missing(storage: ScanStorage) -> None:
    scan_id = new_scan_id()
    workspace = storage.create(scan_id)
    (workspace.source_dir / "app.py").write_text("print('x')\n")

    storage.delete(scan_id)
    storage.delete(scan_id)

    assert not workspace.root.exists()


def test_purge_removes_only_workspaces_older_than_retention(storage: ScanStorage) -> None:
    old_id, fresh_id = new_scan_id(), new_scan_id()
    age_workspace(storage.create(old_id).root, timedelta(hours=25))
    age_workspace(storage.create(fresh_id).root, timedelta(hours=1))

    removed = storage.purge_expired(RETENTION, NOW)

    assert removed == [old_id]
    assert not storage.workspace(old_id).root.exists()
    assert storage.workspace(fresh_id).root.exists()


def test_purge_leaves_unrelated_entries_alone(storage: ScanStorage, tmp_path: Path) -> None:
    unrelated = tmp_path / "storage" / "keep-me"
    unrelated.mkdir(parents=True)
    age_workspace(unrelated, timedelta(days=30))

    assert storage.purge_expired(RETENTION, NOW) == []
    assert unrelated.exists()


def test_purge_skips_workspace_deleted_while_purging(
    storage: ScanStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired_id, vanished_id = new_scan_id(), new_scan_id()
    expired = storage.create(expired_id).root
    age_workspace(expired, timedelta(days=2))
    vanished = storage.workspace(vanished_id).root
    root = expired.parent
    original_iterdir, original_is_dir = Path.iterdir, Path.is_dir

    # The vanished workspace is listed and still looks like a directory, but is gone
    # by the time its timestamps are read, as when delete() runs concurrently.
    def iterdir(self: Path) -> Iterator[Path]:
        entries = original_iterdir(self)
        return iter([vanished, *entries]) if self == root else entries

    def is_dir(self: Path, *args: Any, **kwargs: Any) -> bool:
        return self == vanished or original_is_dir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    monkeypatch.setattr(Path, "is_dir", is_dir)

    assert storage.purge_expired(RETENTION, NOW) == [expired_id]
    assert not expired.exists()


def test_purge_leaves_files_named_like_scan_ids_alone(storage: ScanStorage, tmp_path: Path) -> None:
    stray = tmp_path / "storage" / new_scan_id()
    stray.parent.mkdir(parents=True)
    stray.write_text("not a workspace")
    age_workspace(stray, timedelta(days=30))

    assert storage.purge_expired(RETENTION, NOW) == []
    assert stray.exists()


def test_purge_handles_missing_storage_root(storage: ScanStorage) -> None:
    assert storage.purge_expired(RETENTION, NOW) == []
