import os
from pathlib import Path

import pytest

from app.errors import IngestError, IngestRejection
from app.ingest.directory import ingest_directory
from app.ingest.models import IngestLimits, SkippedFile, SkipReason


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


def test_enforces_file_count_and_total_size_limits(project: Path, tmp_path: Path) -> None:
    with pytest.raises(IngestError) as too_many:
        ingest_directory(project, tmp_path / "a", IngestLimits(max_files=2))
    with pytest.raises(IngestError) as too_big:
        ingest_directory(project, tmp_path / "b", IngestLimits(max_total_uncompressed_bytes=20))

    assert too_many.value.reason is IngestRejection.TOO_MANY_FILES
    assert too_big.value.reason is IngestRejection.UNCOMPRESSED_TOO_LARGE
