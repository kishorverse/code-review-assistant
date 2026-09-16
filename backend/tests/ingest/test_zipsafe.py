import io
import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from app.errors import IngestError, IngestRejection
from app.ingest.models import MB, IngestLimits, SkippedFile, SkipReason
from app.ingest.zipsafe import extract_archive, write_limited

LIMITS = IngestLimits()


def make_zip(
    path: Path, entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED
) -> Path:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def files_under(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file()) if directory.exists() else []


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    return tmp_path / "scan" / "source"


def extract_expecting(
    archive: Path, destination: Path, reason: IngestRejection, limits: IngestLimits = LIMITS
) -> IngestError:
    with pytest.raises(IngestError) as caught:
        extract_archive(archive, destination, limits)
    assert caught.value.reason is reason
    assert files_under(destination) == []
    return caught.value


# --- happy path ------------------------------------------------------------------------------


def test_extracts_source_files_with_posix_relative_paths(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(
        tmp_path / "project.zip",
        {
            "app/__init__.py": b"",
            "app/utils/helpers.py": b"def add(a, b):\n    return a + b\n",
            "README.md": b"# Demo\n",
        },
    )

    result = extract_archive(archive, destination, LIMITS)

    assert result.files == ["README.md", "app/__init__.py", "app/utils/helpers.py"]
    assert result.skipped == []
    assert result.root == destination.resolve()
    assert (destination / "app" / "utils" / "helpers.py").read_bytes().startswith(b"def add")


def test_does_not_list_directory_entries_as_files(tmp_path: Path, destination: Path) -> None:
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.mkdir("src")
        zf.writestr("src/main.py", b"print('hi')\n")

    result = extract_archive(archive, destination, LIMITS)

    assert result.files == ["src/main.py"]


def test_skips_filtered_files_without_writing_them(tmp_path: Path, destination: Path) -> None:
    limits = IngestLimits(max_file_bytes=1024)
    archive = make_zip(
        tmp_path / "project.zip",
        {
            "main.py": b"print('kept')\n",
            "node_modules/left-pad/index.js": b"module.exports = 1\n",
            "package-lock.json": b"{}",
            "static/vendor.min.js": b"var a=1;",
            "data/huge.py": b"x = 1\n" * 400,
            "assets/logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
        },
    )

    result = extract_archive(archive, destination, limits)

    assert result.files == ["main.py"]
    assert result.skipped == [
        SkippedFile(path="assets/logo.png", reason=SkipReason.BINARY),
        SkippedFile(path="data/huge.py", reason=SkipReason.TOO_LARGE),
        SkippedFile(path="node_modules/left-pad/index.js", reason=SkipReason.EXCLUDED_DIRECTORY),
        SkippedFile(path="package-lock.json", reason=SkipReason.LOCKFILE),
        SkippedFile(path="static/vendor.min.js", reason=SkipReason.MINIFIED),
    ]
    assert files_under(destination) == [destination / "main.py"]


def test_accepts_small_but_highly_compressible_archive(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "repetitive.zip", {"table.py": b"ROW = (0, 0, 0)\n" * 20_000})

    result = extract_archive(archive, destination, LIMITS)

    assert result.files == ["table.py"]


# --- zip slip and unsafe entries --------------------------------------------------------------


@pytest.mark.parametrize("evil_name", ["../evil.py", "src/../../evil.py", "..\\evil.py"])
def test_rejects_path_traversal_and_writes_nothing(
    tmp_path: Path, destination: Path, evil_name: str
) -> None:
    archive = make_zip(tmp_path / "slip.zip", {"good.py": b"ok\n", evil_name: b"pwned\n"})

    extract_expecting(archive, destination, IngestRejection.PATH_TRAVERSAL)

    assert not (tmp_path / "evil.py").exists()
    assert not (tmp_path / "scan" / "evil.py").exists()


def test_rejects_absolute_path_entry(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "absolute.zip", {"/etc/cron.d/evil": b"* * * * * root evil\n"})

    extract_expecting(archive, destination, IngestRejection.PATH_TRAVERSAL)


def test_rejects_symlink_entry(tmp_path: Path, destination: Path) -> None:
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        link = zipfile.ZipInfo("config.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, b"/etc/passwd")

    error = extract_expecting(archive, destination, IngestRejection.SYMLINK)

    assert "config.py" in error.message


def test_rejects_encrypted_entry(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "encrypted.zip", {"secret.py": b"not really encrypted"})
    # zipfile cannot write encrypted entries, so set the "encrypted" general purpose flag
    # (offset 8 of the central directory header) the way a real encrypting tool would.
    data = bytearray(archive.read_bytes())
    header = data.index(b"PK\x01\x02")
    data[header + 8] |= 0x1
    archive.write_bytes(bytes(data))

    extract_expecting(archive, destination, IngestRejection.ENCRYPTED_ENTRY)


def test_rejects_duplicate_entries_that_differ_only_in_case(
    tmp_path: Path, destination: Path
) -> None:
    archive = tmp_path / "duplicate.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        make_zip(archive, {"App.py": b"one\n", "app.py": b"two\n"})

    extract_expecting(archive, destination, IngestRejection.DUPLICATE_ENTRY)


def test_rejects_path_used_as_both_file_and_directory(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "clash.zip", {"src": b"file\n", "src/main.py": b"code\n"})

    extract_expecting(archive, destination, IngestRejection.DUPLICATE_ENTRY)


# --- size limits and zip bombs ----------------------------------------------------------------


def test_rejects_archive_larger_than_compressed_limit(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "big.zip", {"a.py": b"x" * 5000}, compression=zipfile.ZIP_STORED)

    extract_expecting(
        archive,
        destination,
        IngestRejection.ARCHIVE_TOO_LARGE,
        IngestLimits(max_archive_bytes=1000),
    )


def test_rejects_archive_with_too_many_files(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "many.zip", {f"pkg/m{i}.py": b"" for i in range(6)})

    error = extract_expecting(
        archive, destination, IngestRejection.TOO_MANY_FILES, IngestLimits(max_files=5)
    )

    assert "more than 5 files" in error.message


def test_rejects_total_uncompressed_size_over_limit(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "wide.zip", {f"m{i}.py": b"y = 2\n" * 200 for i in range(3)})

    extract_expecting(
        archive,
        destination,
        IngestRejection.UNCOMPRESSED_TOO_LARGE,
        IngestLimits(max_total_uncompressed_bytes=2000, max_file_bytes=1000),
    )


def test_rejects_zip_bomb_by_compression_ratio(tmp_path: Path, destination: Path) -> None:
    archive = make_zip(tmp_path / "bomb.zip", {"bomb.txt": b"\x00" * (2 * MB)})

    error = extract_expecting(archive, destination, IngestRejection.COMPRESSION_RATIO)

    assert "zip bomb" in error.message


# --- corrupt archives ---------------------------------------------------------------------------


def test_rejects_file_that_is_not_a_zip(tmp_path: Path, destination: Path) -> None:
    fake = tmp_path / "fake.zip"
    fake.write_bytes(b"this is plain text, not an archive")

    extract_expecting(fake, destination, IngestRejection.CORRUPT_ARCHIVE)


def test_removes_already_extracted_files_when_a_later_entry_is_corrupt(
    tmp_path: Path, destination: Path
) -> None:
    archive = make_zip(
        tmp_path / "corrupt.zip",
        {"a_first.py": b"print('extracted first')\n", "b_second.py": b"ORIGINAL-CONTENT-MARKER"},
        compression=zipfile.ZIP_STORED,
    )
    data = archive.read_bytes()
    archive.write_bytes(data.replace(b"ORIGINAL-CONTENT-MARKER", b"TAMPERED-CONTENT-MARKER"))

    extract_expecting(archive, destination, IngestRejection.CORRUPT_ARCHIVE)


def test_write_limited_refuses_content_longer_than_declared(tmp_path: Path) -> None:
    target = tmp_path / "out.py"
    source = io.BytesIO(b"a" * 100)

    with pytest.raises(IngestError) as caught:
        write_limited(iter(lambda: source.read(30), b""), target, max_bytes=64)

    assert caught.value.reason is IngestRejection.SIZE_MISMATCH
    assert target.stat().st_size <= 64


def test_write_limited_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "existing.py"
    target.write_bytes(b"original")

    with pytest.raises(FileExistsError):
        write_limited([b"replacement"], target, max_bytes=100)

    assert target.read_bytes() == b"original"
