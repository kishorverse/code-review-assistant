from pathlib import Path

import pytest

from app.static.python_version import DEFAULT_MINOR, declared_python_minor


def declare(tmp_path: Path, files: dict[str, str]) -> int:
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return declared_python_minor(tmp_path, sorted(files))


@pytest.mark.parametrize(
    ("spec", "minor"),
    [
        (">=3.9", 9),
        (">=3.10,<4", 10),
        ("~=3.12", 12),
        ("==3.13.*", 13),
        (">=3.12, !=3.12.1", 12),
        (">=3.4", 7),
        (">=3.99", 14),
    ],
)
def test_reads_the_lower_bound_of_requires_python(tmp_path: Path, spec: str, minor: int) -> None:
    pyproject = f'[project]\nrequires-python = "{spec}"\n'

    assert declare(tmp_path, {"pyproject.toml": pyproject}) == minor


def test_ruffs_own_target_wins_over_requires_python(tmp_path: Path) -> None:
    pyproject = '[project]\nrequires-python = ">=3.9"\n\n[tool.ruff]\ntarget-version = "py312"\n'

    assert declare(tmp_path, {"pyproject.toml": pyproject}) == 12


def test_the_top_most_pyproject_is_used(tmp_path: Path) -> None:
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.12"\n',
        "vendor/old/pyproject.toml": '[project]\nrequires-python = ">=3.8"\n',
    }

    assert declare(tmp_path, files) == 12


@pytest.mark.parametrize(
    "files",
    [
        {"app.py": "print(1)\n"},
        {"pyproject.toml": "[project\n"},
        {"pyproject.toml": "[project]\nrequires-python = 3.9\n"},
        {"pyproject.toml": '[project]\nrequires-python = "<4"\n'},
        {"pyproject.toml": '[tool.ruff]\ntarget-version = "latest"\n'},
        {"pyproject.toml": "tool = 1\nproject = []\n"},
    ],
    ids=["none", "invalid-toml", "not-a-string", "no-lower-bound", "unknown-target", "odd-types"],
)
def test_falls_back_to_the_default_when_nothing_usable_is_declared(
    tmp_path: Path, files: dict[str, str]
) -> None:
    assert declare(tmp_path, files) == DEFAULT_MINOR
