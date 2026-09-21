from pathlib import Path

import pytest

from app.static.declared import (
    DEFAULT_LINE_LENGTH,
    DEFAULT_MINOR,
    FORMATTER_LINE_LENGTH,
    MAX_LINE_LENGTH,
    Declared,
    declared_settings,
)


def declare(tmp_path: Path, files: dict[str, str]) -> Declared:
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return declared_settings(tmp_path, sorted(files))


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

    assert declare(tmp_path, {"pyproject.toml": pyproject}).python_minor == minor


def test_ruffs_own_target_wins_over_requires_python(tmp_path: Path) -> None:
    pyproject = '[project]\nrequires-python = ">=3.9"\n\n[tool.ruff]\ntarget-version = "py312"\n'

    assert declare(tmp_path, {"pyproject.toml": pyproject}).python_minor == 12


def test_the_top_most_pyproject_is_used(tmp_path: Path) -> None:
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.12"\n',
        "vendor/old/pyproject.toml": '[project]\nrequires-python = ">=3.8"\n',
    }

    assert declare(tmp_path, files).python_minor == 12


@pytest.mark.parametrize(
    ("pyproject", "length"),
    [
        ("[tool.ruff]\nline-length = 100\n", 100),
        ("[tool.black]\nline-length = 88\n", 88),
        (
            "[tool.ruff]\nline-length = 100\n[tool.ruff.lint.pycodestyle]\nmax-line-length = 110\n",
            110,
        ),
        ("[tool.ruff]\nline-length = 72\n", 72),
        ("[tool.ruff]\nline-length = 10000\n", MAX_LINE_LENGTH),
        ("[tool.ruff]\nline-length = true\n", FORMATTER_LINE_LENGTH),
        ('[tool.ruff]\nline-length = "100"\n', FORMATTER_LINE_LENGTH),
    ],
    ids=["ruff", "black", "pycodestyle-wins", "stricter", "capped", "bool", "string"],
)
def test_reads_the_declared_line_length(tmp_path: Path, pyproject: str, length: int) -> None:
    assert declare(tmp_path, {"pyproject.toml": pyproject}).line_length == length


@pytest.mark.parametrize(
    "pyproject",
    [
        '[tool.ruff]\ntarget-version = "py312"\n',
        "[tool.ruff.lint]\nselect = []\n",
        "[tool.black]\nskip-string-normalization = true\n",
    ],
    ids=["ruff", "ruff-subtable", "black"],
)
def test_a_project_that_configures_a_formatter_gets_its_default_width(
    tmp_path: Path, pyproject: str
) -> None:
    """Ruff and Black format at 88, so a project that adopted one agreed to 88.

    Measuring such a project against PEP 8's 79 reports most of its longer lines:
    requests and click each configure Ruff without a width, and scanning them at 79
    produced 289 and 755 line-length findings.
    """
    assert declare(tmp_path, {"pyproject.toml": pyproject}).line_length == FORMATTER_LINE_LENGTH


def test_a_target_version_ruff_does_not_recognize_leaves_the_default_python(
    tmp_path: Path,
) -> None:
    pyproject = '[tool.ruff]\ntarget-version = "latest"\n'

    assert declare(tmp_path, {"pyproject.toml": pyproject}).python_minor == DEFAULT_MINOR


def test_pep_8_still_applies_to_a_project_that_configures_no_formatter(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "plain"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'

    assert declare(tmp_path, {"pyproject.toml": pyproject}).line_length == DEFAULT_LINE_LENGTH


@pytest.mark.parametrize(
    "files",
    [
        {"app.py": "print(1)\n"},
        {"pyproject.toml": "[project\n"},
        {"pyproject.toml": "[project]\nrequires-python = 3.9\n"},
        {"pyproject.toml": '[project]\nrequires-python = "<4"\n'},
        {"pyproject.toml": "tool = 1\nproject = []\n"},
    ],
    ids=["none", "invalid-toml", "not-a-string", "no-lower-bound", "odd-types"],
)
def test_falls_back_to_the_defaults_when_nothing_usable_is_declared(
    tmp_path: Path, files: dict[str, str]
) -> None:
    assert declare(tmp_path, files) == Declared(DEFAULT_MINOR, DEFAULT_LINE_LENGTH)
