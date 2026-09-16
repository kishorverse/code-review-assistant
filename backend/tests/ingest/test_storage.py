import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


def test_create_makes_upload_and_source_directories(storage: ScanStorage, tmp_path: Path) -> None:
    scan_id = new_scan_id()

    workspace = storage.create(scan_id)

    assert workspace.root == tmp_path / "storage" / scan_id
    assert workspace.upload_dir.is_dir()
    assert workspace.source_dir.is_dir()


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


def test_purge_handles_missing_storage_root(storage: ScanStorage) -> None:
    assert storage.purge_expired(RETENTION, NOW) == []
