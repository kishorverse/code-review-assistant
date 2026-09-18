"""The Python version an upload declares, for rules that depend on it.

Ruff runs in isolated mode, so it never reads the upload's configuration and would
otherwise assume its own default target. That default predates Python 3.11, and code
using newer builtins such as ``ExceptionGroup`` was reported as using undefined names.
"""

import re
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MINOR = 11
"""Assumed when an upload declares nothing: Python 3.10 reaches end of life in October 2026."""
OLDEST_MINOR = 7
NEWEST_MINOR = 14
"""The range Ruff can target; a declaration outside it is clamped."""

_LOWER_BOUND = re.compile(r"(?:>=|~=|==|>)\s*3\.(\d+)")
_RUFF_TARGET = re.compile(r"py3(\d+)")


def declared_python_minor(root: Path, files: Sequence[str]) -> int:
    """The oldest Python 3 minor version the upload supports.

    Read from the top-most ``pyproject.toml``: Ruff's ``target-version`` if set, else the
    lower bound of ``requires-python``. The file is only parsed, never executed.

    Args:
        root: Directory the upload was extracted to.
        files: POSIX paths relative to ``root``.
    """
    manifests = [name for name in files if PurePosixPath(name).name == "pyproject.toml"]
    if not manifests:
        return DEFAULT_MINOR
    top = min(manifests, key=lambda name: (name.count("/"), name))
    try:
        data = tomllib.loads((root / top).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return DEFAULT_MINOR
    minor = _ruff_target(data)
    if minor is None:
        minor = _requires_python(data)
    if minor is None:
        return DEFAULT_MINOR
    return max(OLDEST_MINOR, min(NEWEST_MINOR, minor))


def _ruff_target(data: dict[str, Any]) -> int | None:
    tool = data.get("tool")
    ruff = tool.get("ruff") if isinstance(tool, dict) else None
    target = ruff.get("target-version") if isinstance(ruff, dict) else None
    match = _RUFF_TARGET.fullmatch(target) if isinstance(target, str) else None
    return int(match.group(1)) if match else None


def _requires_python(data: dict[str, Any]) -> int | None:
    project = data.get("project")
    spec = project.get("requires-python") if isinstance(project, dict) else None
    if not isinstance(spec, str):
        return None
    bounds = [int(minor) for minor in _LOWER_BOUND.findall(spec)]
    return min(bounds) if bounds else None
