from pathlib import Path

from app.languages.base import SupportLevel
from app.languages.java import JAVA
from app.languages.python import PYTHON
from app.languages.registry import default_registry
from app.preprocess.models import ChunkingConfig, LineRange, PreprocessedFile
from app.preprocess.source_file import preprocess_file, preprocess_source

CONFIG = ChunkingConfig()
REGISTRY = default_registry()


def covered_lines(result: PreprocessedFile) -> set[int]:
    return {n for chunk in result.chunks for n in range(chunk.lines.start, chunk.lines.end + 1)}


def generated_module(functions: int, body_lines: int) -> bytes:
    parts = ['"""Generated module."""', "import math", "from typing import Any", ""]
    for number in range(functions):
        parts.append(f"def compute_{number}(value: Any) -> float:")
        parts.extend(f"    value = math.sqrt(value) + {step}" for step in range(body_lines))
        parts.extend(["    return value", "", ""])
    return ("\n".join(parts) + "\n").encode()


def test_large_file_is_chunked_within_limits_with_every_line_reviewed() -> None:
    source = generated_module(functions=60, body_lines=20)

    result = preprocess_source("pkg/generated.py", source, PYTHON, CONFIG)

    assert result.line_count > 1300
    assert result.support is SupportLevel.FULL
    assert all(chunk.lines.length <= CONFIG.max_lines for chunk in result.chunks)
    assert all(chunk.lines.length <= CONFIG.target_lines for chunk in result.chunks)
    assert covered_lines(result) == set(range(1, result.line_count + 1))
    assert [chunk.index for chunk in result.chunks] == list(range(len(result.chunks)))


def test_later_chunks_carry_imports_as_numbered_context() -> None:
    result = preprocess_source("pkg/generated.py", generated_module(40, 20), PYTHON, CONFIG)

    later = result.chunks[1]
    first_line = later.numbered_code.splitlines()[0]
    assert later.context == [LineRange(start=2, end=3)]
    assert first_line.endswith(" | import math")
    assert first_line.strip().startswith("2 |")


def test_oversized_class_chunks_carry_the_class_signature() -> None:
    methods = "".join(
        f"  public int m{n}() {{\n" + "    int x = 1;\n" * 60 + "    return x;\n  }\n"
        for n in range(12)
    )
    source = f"package demo;\n\npublic class Big {{\n{methods}}}\n".encode()

    result = preprocess_source("Big.java", source, JAVA, CONFIG)

    assert len(result.chunks) > 1
    assert all(chunk.lines.length <= CONFIG.max_lines for chunk in result.chunks)
    assert LineRange(start=3, end=3) in result.chunks[-1].context
    assert covered_lines(result) == set(range(1, result.line_count + 1))


def test_broken_code_is_still_chunked_and_marks_partial_regions() -> None:
    source = b"def ok():\n    return 1\n\ndef broken(:\n    return 2\n\nprint(ok())\n"

    result = preprocess_source("broken.py", source, PYTHON, CONFIG)

    assert result.partial_regions
    assert result.partial_regions[0].start == 4
    assert covered_lines(result) == set(range(1, 8))
    assert result.chunks[0].partial_regions == result.partial_regions


def test_crlf_bom_and_invalid_utf8_keep_line_numbers_aligned() -> None:
    source = b"\xef\xbb\xbfimport os\r\n\r\nname = '\xff\xfe'\r\ndef main():\r\n    return name\r\n"

    result = preprocess_source("windows.py", source, PYTHON, CONFIG)

    code_lines = result.chunks[0].numbered_code.splitlines()
    assert result.line_count == 5
    assert code_lines[0] == "1 | import os"
    assert code_lines[3] == "4 | def main():"
    assert not any("\r" in line for line in code_lines)
    assert "�" in code_lines[2]


def test_empty_and_blank_files_produce_no_chunks() -> None:
    assert preprocess_source("empty.py", b"", PYTHON, CONFIG).chunks == []
    assert preprocess_source("blank.py", b"\n\n   \n", PYTHON, CONFIG).chunks == []


def test_preprocess_file_detects_language_and_skips_unsupported_files(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "manage").write_bytes(b"#!/usr/bin/env python3\nprint('hi')\n")
    (tmp_path / "README.md").write_bytes(b"# Project\n")

    script = preprocess_file(tmp_path, "bin/manage", REGISTRY, CONFIG)

    assert script is not None
    assert script.language == "python"
    assert script.path == "bin/manage"
    assert preprocess_file(tmp_path, "README.md", REGISTRY, CONFIG) is None
