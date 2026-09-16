import pytest

from app.preprocess.chunker import (
    GAP_MARKER,
    build_chunks,
    pack_segments,
    render_numbered,
    select_context,
    split_lines,
)
from app.preprocess.models import ChunkingConfig, LineRange
from app.preprocess.structure import Segment


def lr(start: int, end: int) -> LineRange:
    return LineRange(start=start, end=end)


def seg(start: int, end: int, *context: LineRange) -> Segment:
    return Segment(lines=lr(start, end), context=tuple(context))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\nb\n", ["a", "b"]),
        ("a\nb", ["a", "b"]),
        ("a\r\nb\r\n", ["a", "b"]),
        ("a\n\n", ["a", ""]),
        ("", []),
        ("x\u2028y\n", ["x\u2028y"]),
    ],
)
def test_split_lines_counts_only_newlines(text: str, expected: list[str]) -> None:
    assert split_lines(text) == expected


def test_pack_segments_groups_neighbors_up_to_the_target() -> None:
    segments = [seg(1, 40), seg(41, 90), seg(91, 100), seg(101, 400), seg(401, 420)]

    groups = pack_segments(segments, target_lines=100)

    assert [[s.lines.start for s in group] for group in groups] == [[1, 41, 91], [101], [401]]


def test_render_numbered_right_aligns_numbers_and_marks_gaps() -> None:
    lines = [f"line {number}" for number in range(1, 101)]

    rendered = render_numbered(lines, [lr(1, 2), lr(98, 99)])

    assert rendered.splitlines() == [
        "  1 | line 1",
        "  2 | line 2",
        f"    | {GAP_MARKER}",
        " 98 | line 98",
        " 99 | line 99",
    ]


def test_context_prefers_signatures_then_imports_and_never_repeats_body_lines() -> None:
    body = lr(30, 60)
    signatures = [lr(10, 10), lr(25, 27)]
    header = [lr(1, 5), lr(40, 41)]

    context = select_context(body, signatures, header, max_lines=6)

    assert context == [lr(1, 2), lr(10, 10), lr(25, 27)]


def test_context_skips_parts_already_inside_the_body() -> None:
    assert select_context(lr(1, 50), [lr(1, 1)], [lr(1, 3)], max_lines=40) == []


def test_build_chunks_numbers_lines_clips_partial_regions_and_drops_blank_chunks() -> None:
    lines = [
        "import os",
        "",
        "class Box:",
        "    def open(self):",
        "        return os.getcwd(",
        "",
        "",
    ]
    segments = [seg(1, 2), seg(3, 3, lr(3, 3)), seg(4, 5, lr(3, 3)), seg(6, 7)]

    chunks = build_chunks(
        file_path="pkg/box.py",
        language="python",
        lines=lines,
        segments=segments,
        header=[lr(1, 1)],
        partial_regions=[lr(5, 7)],
        config=ChunkingConfig(target_lines=2, max_lines=4, max_context_lines=10),
    )

    assert [chunk.lines for chunk in chunks] == [lr(1, 2), lr(3, 3), lr(4, 5)]
    assert [chunk.index for chunk in chunks] == [0, 1, 2]
    method = chunks[2]
    assert method.context == [lr(1, 1), lr(3, 3)]
    assert method.partial_regions == [lr(5, 5)]
    assert method.numbered_code.splitlines() == [
        "1 | import os",
        f"  | {GAP_MARKER}",
        "3 | class Box:",
        "4 |     def open(self):",
        "5 |         return os.getcwd(",
    ]
