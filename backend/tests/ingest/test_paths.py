from pathlib import PurePosixPath

import pytest

from app.errors import IngestError, IngestRejection
from app.ingest.paths import safe_relative_path

MAX_LENGTH = 400


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("app.py", "app.py"),
        ("src/pkg/module.py", "src/pkg/module.py"),
        ("src\\pkg\\module.py", "src/pkg/module.py"),
        ("./src//module.py", "src/module.py"),
        ("project/", "project"),
        (".env", ".env"),
        ("docs/..hidden.md", "docs/..hidden.md"),
        ("naïve/ünïcode.py", "naïve/ünïcode.py"),
    ],
)
def test_accepts_and_normalizes_safe_names(name: str, expected: str) -> None:
    assert safe_relative_path(name, MAX_LENGTH) == PurePosixPath(expected)


@pytest.mark.parametrize(
    "name",
    [
        "../evil.py",
        "src/../../evil.py",
        "..\\evil.py",
        "src\\..\\..\\evil.py",
        "..",
    ],
)
def test_rejects_parent_traversal(name: str) -> None:
    with pytest.raises(IngestError) as caught:
        safe_relative_path(name, MAX_LENGTH)

    assert caught.value.reason is IngestRejection.PATH_TRAVERSAL


@pytest.mark.parametrize(
    "name",
    [
        "/etc/passwd",
        "\\Windows\\System32\\evil.dll",
        "C:/Windows/evil.py",
        "C:evil.py",
        "\\\\server\\share\\evil.py",
        "//server/share/evil.py",
    ],
)
def test_rejects_absolute_and_drive_paths(name: str) -> None:
    with pytest.raises(IngestError) as caught:
        safe_relative_path(name, MAX_LENGTH)

    assert caught.value.reason is IngestRejection.PATH_TRAVERSAL


@pytest.mark.parametrize(
    "name",
    [
        "",
        "./",
        "src/app.py:hidden-stream",
        "bad\x00name.py",
        "tab\tname.py",
        "what?.py",
        "CON.py",
        "con .txt",
        "CONIN$",
        "conout$.log",
        "src/clock$",
        "COM¹.txt",
        "lpt³",
        "src/nul",
        "lpt1.txt",
        "trailing-dot.",
        "trailing-space ",
        "a" * 256,
    ],
)
def test_rejects_empty_or_non_portable_names(name: str) -> None:
    with pytest.raises(IngestError) as caught:
        safe_relative_path(name, MAX_LENGTH)

    assert caught.value.reason is IngestRejection.INVALID_PATH


def test_rejects_names_longer_than_limit() -> None:
    with pytest.raises(IngestError) as caught:
        safe_relative_path("dir/" * 30 + "file.py", max_length=100)

    assert caught.value.reason is IngestRejection.INVALID_PATH


def test_error_message_does_not_echo_raw_control_characters() -> None:
    with pytest.raises(IngestError) as caught:
        safe_relative_path("evil\x1b[31mname.py", MAX_LENGTH)

    assert "\x1b" not in caught.value.message
