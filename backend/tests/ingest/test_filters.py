from pathlib import PurePosixPath

import pytest

from app.ingest.filters import BINARY_SNIFF_BYTES, skip_reason_for_content, skip_reason_for_path
from app.ingest.models import SkipReason

MAX_FILE_BYTES = 1024


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("node_modules/lodash/index.js", SkipReason.EXCLUDED_DIRECTORY),
        ("web/node_modules/react/index.js", SkipReason.EXCLUDED_DIRECTORY),
        (".git/config", SkipReason.EXCLUDED_DIRECTORY),
        (".venv/lib/site.py", SkipReason.EXCLUDED_DIRECTORY),
        ("pkg/__pycache__/mod.cpython-312.pyc", SkipReason.EXCLUDED_DIRECTORY),
        ("frontend/dist/assets/app.js", SkipReason.EXCLUDED_DIRECTORY),
        ("Node_Modules/pkg/index.js", SkipReason.EXCLUDED_DIRECTORY),
        ("package-lock.json", SkipReason.LOCKFILE),
        ("backend/uv.lock", SkipReason.LOCKFILE),
        ("Cargo.lock", SkipReason.LOCKFILE),
        ("static/vendor/jquery.min.js", SkipReason.MINIFIED),
        ("static/app.css.map", SkipReason.MINIFIED),
    ],
)
def test_skips_dependencies_lockfiles_and_generated_files(path: str, expected: SkipReason) -> None:
    assert skip_reason_for_path(PurePosixPath(path)) is expected


@pytest.mark.parametrize(
    "path",
    [
        "app/main.py",
        "src/components/App.tsx",
        "build.py",
        "scripts/build",
        "docs/distribution.md",
        "requirements.txt",
        "package.json",
    ],
)
def test_keeps_source_files_including_names_that_resemble_excluded_ones(path: str) -> None:
    assert skip_reason_for_path(PurePosixPath(path)) is None


def test_skips_files_over_the_size_limit() -> None:
    assert skip_reason_for_content(MAX_FILE_BYTES + 1, b"x", MAX_FILE_BYTES) is SkipReason.TOO_LARGE


def test_keeps_file_exactly_at_the_size_limit() -> None:
    assert skip_reason_for_content(MAX_FILE_BYTES, b"print('hi')\n", MAX_FILE_BYTES) is None


def test_skips_binary_content() -> None:
    head = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    assert skip_reason_for_content(len(head), head, MAX_FILE_BYTES) is SkipReason.BINARY


def test_only_sniffs_the_first_block_for_binary_markers() -> None:
    head = b"a" * BINARY_SNIFF_BYTES + b"\x00"

    assert skip_reason_for_content(len(head), head, len(head)) is None


def test_keeps_utf8_text_with_non_ascii_characters() -> None:
    head = "# résumé → naïve\n".encode()

    assert skip_reason_for_content(len(head), head, MAX_FILE_BYTES) is None
