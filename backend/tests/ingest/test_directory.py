import os
import threading
from pathlib import Path
from typing import Any

import pytest

from app.errors import IngestError, IngestRejection
from app.ingest.directory import ingest_directory
from app.ingest.models import IngestLimits, IngestResult, SkippedFile, SkipReason


def write(root: Path, name: str, content: bytes | str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode()
    path.write_bytes(content)
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    write(root, "app/main.py", "print('hi')\n")
    write(root, "app/utils/helpers.py", "def help():\n    return 1\n")
    write(root, "README.md", "# Project\n")
    write(root, "node_modules/left-pad/index.js", "module.exports = 1\n")
    write(root, ".git/config", "[core]\n")
    write(root, "package-lock.json", "{}")
    write(root, "static/logo.png", b"\x89PNG\r\n\x1a\n\x00\x00")
    write(root, "data/huge.py", "x = 1\n" * 400)
    return root


def test_copies_reviewable_files_and_reports_what_was_skipped(
    project: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "scan" / "source"

    result = ingest_directory(project, destination, IngestLimits(max_file_bytes=1024))

    assert result.files == ["README.md", "app/main.py", "app/utils/helpers.py"]
    assert result.skipped == [
        SkippedFile(path=".git", reason=SkipReason.EXCLUDED_DIRECTORY),
        SkippedFile(path="data/huge.py", reason=SkipReason.TOO_LARGE),
        SkippedFile(path="node_modules", reason=SkipReason.EXCLUDED_DIRECTORY),
        SkippedFile(path="package-lock.json", reason=SkipReason.LOCKFILE),
        SkippedFile(path="static/logo.png", reason=SkipReason.BINARY),
    ]
    assert (
        destination / "app" / "utils" / "helpers.py"
    ).read_text() == "def help():\n    return 1\n"
    assert not (destination / "node_modules").exists()
    assert result.root == destination.resolve()


def test_never_follows_symbolic_links(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    write(outside, "secret.py", "TOKEN = 1\n")
    try:
        os.symlink(outside, project / "linked_dir", target_is_directory=True)
        os.symlink(outside / "secret.py", project / "linked.py")
    except OSError:
        pytest.skip("creating symlinks requires extra privileges on this platform")

    result = ingest_directory(project, tmp_path / "dest", IngestLimits())

    assert SkippedFile(path="linked_dir", reason=SkipReason.SYMLINK) in result.skipped
    assert SkippedFile(path="linked.py", reason=SkipReason.SYMLINK) in result.skipped
    assert not any("secret" in name for name in result.files)


def test_unreadable_files_are_skipped_instead_of_failing_the_scan(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = project / "app" / "main.py"
    original_open = Path.open

    def deny_locked(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == locked:
            raise PermissionError(13, "Permission denied", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_locked)

    result = ingest_directory(project, tmp_path / "dest", IngestLimits(max_file_bytes=1024))

    assert SkippedFile(path="app/main.py", reason=SkipReason.UNREADABLE) in result.skipped
    assert "app/utils/helpers.py" in result.files


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are POSIX-only")
def test_named_pipes_are_skipped_without_blocking(project: Path, tmp_path: Path) -> None:
    os.mkfifo(project / "app" / "events.pipe")
    outcome: dict[str, object] = {}

    def scan() -> None:
        outcome["result"] = ingest_directory(project, tmp_path / "dest", IngestLimits())

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive(), "ingest blocked on a named pipe"
    result = outcome["result"]
    assert isinstance(result, IngestResult)
    assert SkippedFile(path="app/events.pipe", reason=SkipReason.SPECIAL_FILE) in result.skipped


def test_enforces_file_count_and_total_size_limits(project: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as too_many:
        ingest_directory(project, tmp_path / "a", IngestLimits(max_files=2))
    with pytest.raises(IngestError) as too_big:
        ingest_directory(project, tmp_path / "b", IngestLimits(max_total_uncompressed_bytes=20))

    assert too_many.value.reason is IngestRejection.TOO_MANY_FILES
    assert too_big.value.reason is IngestRejection.UNCOMPRESSED_TOO_LARGE
