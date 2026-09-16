from pathlib import PurePosixPath

import pytest

from app.languages.registry import default_registry
from app.preprocess.detect import detect_language

REGISTRY = default_registry()


def detected(name: str, head: bytes = b"") -> str | None:
    adapter = detect_language(PurePosixPath(name), head, REGISTRY)
    return adapter.name if adapter else None


def test_extension_wins_over_shebang() -> None:
    assert detected("tool.js", b"#!/usr/bin/env python3\n") == "javascript"


def test_unknown_extension_is_not_reviewed_even_with_shebang() -> None:
    assert detected("deploy.sh", b"#!/usr/bin/env python3\n") is None


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"#!/usr/bin/env python3\nprint('hi')\n", "python"),
        (b"#!/usr/bin/python3.12\n", "python"),
        (b"#! /usr/local/bin/python\r\n", "python"),
        (b"#!/usr/bin/env node\n", "javascript"),
        (b"#!/bin/bash\necho hi\n", None),
        (b"print('no shebang')\n", None),
        (b"", None),
    ],
)
def test_extensionless_scripts_are_detected_by_shebang(head: bytes, expected: str | None) -> None:
    assert detected("bin/manage", head) == expected
