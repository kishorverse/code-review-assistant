"""Decide which language a file is written in.

The extension decides first. Only files without an extension are checked for
a shebang such as ``#!/usr/bin/env python3``, which is how scripts are
usually identified.
"""

import re
from pathlib import PurePosixPath

from app.languages.base import LanguageAdapter
from app.languages.registry import LanguageRegistry

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
    interpreter = shebang_interpreter(head.split(b"\n", 1)[0])
    if interpreter is None:
        return None
    return registry.by_interpreter(interpreter) or registry.by_interpreter(
        _VERSION_SUFFIX.sub("", interpreter)
    )


def shebang_interpreter(first_line: bytes) -> str | None:
    """Return the interpreter a shebang line runs, ignoring its arguments.

    Handles ``#!/usr/bin/python3 -O`` as well as ``/usr/bin/env`` forms, where
    env's own options (``-S``, ``-i``) and ``NAME=value`` assignments come
    before the interpreter.
    """
    line = first_line.strip().decode(errors="replace")
    if not line.startswith("#!"):
        return None
    words = line[2:].split()
    if not words:
        return None
    program = PurePosixPath(words[0]).name
    if program != "env":
        return program
    return next(
        (word for word in words[1:] if not word.startswith("-") and "=" not in word),
        None,
    )
