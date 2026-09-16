import zipfile
from pathlib import Path

import pytest

from app.errors import IngestError, IngestRejection
from app.ingest.models import IngestLimits, SkippedFile, SkipReason
from app.ingest.upload import ingest_upload

LIMITS = IngestLimits(max_file_bytes=1024)


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    return tmp_path / "source"


def saved_upload(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "upload.bin"
    path.write_bytes(content)
    return path


def test_routes_zip_uploads_to_archive_extraction_regardless_of_case(
    tmp_path: Path, destination: Path
) -> None:
    upload = tmp_path / "upload.bin"
    with zipfile.ZipFile(upload, "w") as archive:
        archive.writestr("pkg/app.py", b"print('from zip')\n")

    result = ingest_upload(upload, "Project.ZIP", destination, LIMITS)

    assert result.files == ["pkg/app.py"]


def test_copies_single_source_file_using_only_the_base_name(
    tmp_path: Path, destination: Path
) -> None:
    upload = saved_upload(tmp_path, b"def main():\n    return 0\n")

    result = ingest_upload(upload, "C:\\Users\\dev\\project\\main.py", destination, LIMITS)

    assert result.files == ["main.py"]
    assert result.skipped == []
    assert (destination / "main.py").read_bytes() == b"def main():\n    return 0\n"


@pytest.mark.parametrize(
    ("filename", "content", "reason"),
    [
        ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00", SkipReason.BINARY),
        ("package-lock.json", b"{}", SkipReason.LOCKFILE),
        ("bundle.min.js", b"var a=1;", SkipReason.MINIFIED),
        ("big.py", b"x = 1\n" * 300, SkipReason.TOO_LARGE),
    ],
)
def test_reports_skipped_single_file_without_writing_it(
    tmp_path: Path, destination: Path, filename: str, content: bytes, reason: SkipReason
) -> None:
    upload = saved_upload(tmp_path, content)

    result = ingest_upload(upload, filename, destination, LIMITS)

    assert result.files == []
    assert result.skipped == [SkippedFile(path=filename, reason=reason)]
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        ("..", IngestRejection.PATH_TRAVERSAL),
        ("", IngestRejection.INVALID_PATH),
        ("CON.py", IngestRejection.INVALID_PATH),
        ("notes.py:stream", IngestRejection.INVALID_PATH),
    ],
)
def test_rejects_unsafe_single_file_names(
    tmp_path: Path, destination: Path, filename: str, reason: IngestRejection
) -> None:
    upload = saved_upload(tmp_path, b"print('hi')\n")

    with pytest.raises(IngestError) as caught:
        ingest_upload(upload, filename, destination, LIMITS)

    assert caught.value.reason is reason
