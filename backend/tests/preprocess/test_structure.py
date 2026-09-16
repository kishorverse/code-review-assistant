import textwrap

import pytest

from app.languages.base import LanguageAdapter
from app.languages.go import GO
from app.languages.java import JAVA
from app.languages.javascript import JAVASCRIPT, TYPESCRIPT
from app.languages.python import PYTHON
from app.preprocess.models import LineRange
from app.preprocess.parse import parse_source
from app.preprocess.structure import Segment, header_ranges, segment_file


def source_of(code: str) -> bytes:
    return textwrap.dedent(code).lstrip("\n").encode()


def line_count(source: bytes) -> int:
    return source.count(b"\n") + (0 if source.endswith(b"\n") or not source else 1)


def segments_of(code: str, adapter: LanguageAdapter, max_lines: int = 500) -> list[Segment]:
    source = source_of(code)
    root = parse_source(source, adapter).tree.root_node
    return segment_file(root, line_count(source), adapter, max_lines)


def spans(segments: list[Segment]) -> list[tuple[int, int]]:
    return [(segment.lines.start, segment.lines.end) for segment in segments]


def lr(start: int, end: int) -> LineRange:
    return LineRange(start=start, end=end)


def big_python_class(methods: int = 4, body_lines: int = 8) -> str:
    lines = ["class Service(Base):", '    """Handles requests."""', ""]
    for number in range(methods):
        lines.append(f"    def method_{number}(self, value):")
        lines.extend(f"        value = value + {step}" for step in range(body_lines))
        lines.extend(["        return value", ""])
    return "\n".join(lines) + "\n"


# --- boundaries -------------------------------------------------------------------------------


def test_each_top_level_statement_starts_a_segment_with_leading_comments_attached() -> None:
    code = """
        import os

        # Helper that returns one.
        def one():
            return 1


        @cache
        def two():
            return 2  # trailing comment stays here
        class Three:
            pass
    """

    assert spans(segments_of(code, PYTHON)) == [(1, 2), (3, 7), (8, 10), (11, 12)]


def test_comment_separated_by_blank_line_stays_with_previous_segment() -> None:
    code = """
        x = 1

        # Unrelated note.

        y = 2
    """

    assert spans(segments_of(code, PYTHON)) == [(1, 4), (5, 5)]


def test_trailing_comment_on_a_code_line_does_not_start_a_segment() -> None:
    code = """
        TIMEOUT = 30  # seconds
        # Retries for flaky networks.
        RETRIES = 3
    """

    assert spans(segments_of(code, PYTHON)) == [(1, 1), (2, 3)]


def test_statements_sharing_a_line_do_not_split_it() -> None:
    assert spans(segments_of("a = 1; b = 2\nc = 3\n", PYTHON)) == [(1, 1), (2, 2)]


def test_empty_file_has_no_segments() -> None:
    assert segment_file(parse_source(b"", PYTHON).tree.root_node, 0, PYTHON, 500) == []


# --- splitting oversized code -------------------------------------------------------------------


def test_oversized_class_is_split_at_methods_with_class_signature_as_context() -> None:
    # Lines 1-3: class line, docstring, blank. Each method then spans 11 lines
    # (def, 8 body lines, return, blank line).
    segments = segments_of(big_python_class(methods=4, body_lines=8), PYTHON, max_lines=15)

    assert spans(segments) == [(1, 3), (4, 14), (15, 25), (26, 36), (37, 47)]
    assert all(segment.context == (lr(1, 1),) for segment in segments)


def test_oversized_method_keeps_class_and_multiline_def_signatures() -> None:
    body = "\n".join(f"        total += {n}" for n in range(30))
    code = f"class Report:\n    def build(\n        self,\n        rows,\n    ):\n{body}\n"

    segments = segments_of(code, PYTHON, max_lines=10)

    assert all(segment.lines.length <= 10 for segment in segments)
    assert segments[-1].context == (lr(1, 1), lr(2, 5))


def test_decorated_and_exported_classes_include_wrapper_lines_in_signature() -> None:
    python = "@dataclass\n" + big_python_class(methods=3, body_lines=8)
    javascript = (
        "export class Big {\n"
        + "".join(f"  method{n}() {{\n" + "    step();\n" * 8 + "  }\n" for n in range(3))
        + "}\n"
    )

    python_segments = segments_of(python, PYTHON, max_lines=15)
    javascript_segments = segments_of(javascript, JAVASCRIPT, max_lines=15)

    assert python_segments[-1].context == (lr(1, 2),)
    assert javascript_segments[-1].context == (lr(1, 1),)
    assert len(javascript_segments) == 3


def test_falls_back_to_windows_when_no_structure_is_left() -> None:
    text = "\n".join(f"line {n}" for n in range(25))
    code = f'MESSAGE = """\n{text}\n"""\n'

    assert spans(segments_of(code, PYTHON, max_lines=10)) == [(1, 10), (11, 20), (21, 27)]


def test_deeply_nested_input_does_not_hit_the_recursion_limit() -> None:
    code = "x = " + "[\n" * 3000 + "]\n" * 3000

    segments = segments_of(code, PYTHON, max_lines=100)

    assert all(segment.lines.length <= 100 for segment in segments)


# --- invariants across languages ----------------------------------------------------------------

SAMPLES: list[tuple[LanguageAdapter, str]] = [
    (PYTHON, big_python_class(methods=6, body_lines=12) + "\n\ndef tail():\n    return 0\n"),
    (
        JAVASCRIPT,
        "import a from 'a';\n// note\n"
        + "".join(f"export function f{n}() {{\n" + "  a();\n" * 15 + "}\n\n" for n in range(5)),
    ),
    (
        TYPESCRIPT,
        "interface Shape { area(): number }\nexport class Box implements Shape {\n"
        + "".join(f"  m{n}(): number {{\n" + "    return 1;\n" * 12 + "  }\n" for n in range(5))
        + "  area(): number { return 0; }\n}\n",
    ),
    (
        JAVA,
        "package demo;\nimport java.util.List;\n\npublic class Big {\n"
        + "".join(
            f"  // method {n}\n  void m{n}() {{\n" + "    run();\n" * 14 + "  }\n" for n in range(5)
        )
        + "}\n",
    ),
    (
        GO,
        'package main\n\nimport "fmt"\n\n'
        + "".join(f"func f{n}() {{\n" + '\tfmt.Println("x")\n' * 20 + "}\n\n" for n in range(4)),
    ),
]


@pytest.mark.parametrize("max_lines", [7, 20, 500])
@pytest.mark.parametrize(("adapter", "code"), SAMPLES, ids=lambda value: getattr(value, "name", ""))
def test_segments_cover_every_line_exactly_once_within_the_limit(
    adapter: LanguageAdapter, code: str, max_lines: int
) -> None:
    source = code.encode()
    total = line_count(source)
    segments = segment_file(parse_source(source, adapter).tree.root_node, total, adapter, max_lines)

    covered = [
        line for segment in segments for line in range(segment.lines.start, segment.lines.end + 1)
    ]
    assert covered == list(range(1, total + 1))
    assert all(segment.lines.length <= max_lines for segment in segments)


def test_header_ranges_merge_adjacent_imports() -> None:
    source = source_of(
        """
        import os
        import sys

        from pathlib import Path

        def main():
            import json
    """
    )

    root = parse_source(source, PYTHON).tree.root_node

    assert header_ranges(root, PYTHON) == [lr(1, 2), lr(4, 4)]
