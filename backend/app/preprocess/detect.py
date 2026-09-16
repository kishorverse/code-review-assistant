"""Decide which language a file is written in.

The extension decides first. Only files without an extension are checked for
a shebang such as ``#!/usr/bin/env python3``, which is how scripts are
usually identified.
"""

import re
from pathlib import PurePosixPath

from app.languages.base import LanguageAdapter
from app.languages.registry import LanguageRegistry

_SHEBANG = re.compile(rb"#!\s*(?P<program>\S+)(?:\s+(?P<argument>\S+))?")
_VERSION_SUFFIX = re.compile(r"[\d.]+$")


def detect_language(
    path: PurePosixPath, head: bytes, registry: LanguageRegistry
) -> LanguageAdapter | None:
    """Return the adapter for a file, or ``None`` if Margin does not review its language.

    Args:
        path: The file's path; only the name is used.
        head: The first bytes of the file, enough to contain a shebang line.
        registry: The available adapters.
    """
    if path.suffix:
        return registry.by_extension(path)
    return _detect_from_shebang(head, registry)


def _detect_from_shebang(head: bytes, registry: LanguageRegistry) -> LanguageAdapter | None:
    first_line = head.split(b"\n", 1)[0].strip()
    match = _SHEBANG.fullmatch(first_line)
    if match is None:
        return None
    interpreter = PurePosixPath(match["program"].decode(errors="replace")).name
    if interpreter == "env" and match["argument"]:
        interpreter = match["argument"].decode(errors="replace")
    return registry.by_interpreter(interpreter) or registry.by_interpreter(
        _VERSION_SUFFIX.sub("", interpreter)
    )
