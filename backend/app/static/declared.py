"""Project settings an upload declares, which the analyzers respect.

Ruff runs in isolated mode, so an upload's configuration cannot switch rules off.
Two settings are read from the top-most ``pyproject.toml`` all the same, because
they describe the project rather than hide findings:

- **Python version.** Which names are builtins depends on it. Ruff's own default
  predates Python 3.11, so code catching ``ExceptionGroup`` was reported as using
  an undefined name.
- **Line length.** PEP 8 lets a team agree on lines longer than 79 characters. A
  project formatted at 100 columns would otherwise get a finding for most of its
  longer lines. The value is capped, so a huge one cannot switch the check off.

The file is only parsed, never executed.
"""

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MINOR = 11
"""Assumed when an upload declares nothing: Python 3.10 reaches end of life in October 2026."""
OLDEST_MINOR = 7
NEWEST_MINOR = 14
"""The range Ruff can target; a declaration outside it is clamped."""
DEFAULT_LINE_LENGTH = 79
"""PEP 8's maximum line length."""
MAX_LINE_LENGTH = 120
"""The longest declared line length honoured."""

_LOWER_BOUND = re.compile(r"(?:>=|~=|==|>)\s*3\.(\d+)")
_RUFF_TARGET = re.compile(r"py3(\d+)")


@dataclass(frozen=True)
class Declared:
    """What an upload declares, with defaults for what it does not.

    Attributes:
        python_minor: The oldest Python 3 minor version the project supports.
        line_length: The maximum line length the project agreed on.
    """

    python_minor: int = DEFAULT_MINOR
    line_length: int = DEFAULT_LINE_LENGTH


def declared_settings(root: Path, files: Sequence[str]) -> Declared:
    """Read the settings from the upload's top-most ``pyproject.toml``.

    Args:
        root: Directory the upload was extracted to.
        files: POSIX paths relative to ``root``.
    """
    data = _top_pyproject(root, files)
    if data is None:
        return Declared()
    minor = _ruff_target(data)
    if minor is None:
        minor = _requires_python(data)
    length = _line_length(data)
    return Declared(
        python_minor=DEFAULT_MINOR
        if minor is None
        else max(OLDEST_MINOR, min(NEWEST_MINOR, minor)),
        line_length=DEFAULT_LINE_LENGTH if length is None else min(MAX_LINE_LENGTH, length),
    )


def _top_pyproject(root: Path, files: Sequence[str]) -> dict[str, Any] | None:
    manifests = [name for name in files if PurePosixPath(name).name == "pyproject.toml"]
    if not manifests:
        return None
    top = min(manifests, key=lambda name: (name.count("/"), name))
    try:
        return tomllib.loads((root / top).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def _table(data: dict[str, Any], *path: str) -> dict[str, Any]:
    for key in path:
        value = data.get(key)
        if not isinstance(value, dict):
            return {}
        data = value
    return data


def _ruff_target(data: dict[str, Any]) -> int | None:
    target = _table(data, "tool", "ruff").get("target-version")
    match = _RUFF_TARGET.fullmatch(target) if isinstance(target, str) else None
    return int(match.group(1)) if match else None


def _requires_python(data: dict[str, Any]) -> int | None:
    spec = _table(data, "project").get("requires-python")
    if not isinstance(spec, str):
        return None
    bounds = [int(minor) for minor in _LOWER_BOUND.findall(spec)]
    return min(bounds) if bounds else None


def _line_length(data: dict[str, Any]) -> int | None:
    # The first that is set, in the order Ruff itself gives them precedence.
    for value in (
        _table(data, "tool", "ruff", "lint", "pycodestyle").get("max-line-length"),
        _table(data, "tool", "ruff").get("line-length"),
        _table(data, "tool", "black").get("line-length"),
    ):
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None
