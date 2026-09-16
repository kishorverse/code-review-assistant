"""Pack segments into review chunks and render them with real line numbers.

Small neighboring segments are packed together up to a target size, which
saves LLM calls. Each chunk carries context lines from outside its body
(enclosing signatures first, then imports) so it can be understood on its
own, and its code is rendered as ``  42 | ...`` so every finding can cite real
file line numbers that the verifier can check.
"""

from collections.abc import Sequence

from app.preprocess.models import Chunk, ChunkingConfig, LineRange, merge_ranges
from app.preprocess.structure import Segment

GAP_MARKER = "..."


def split_lines(text: str) -> list[str]:
    """Split text into lines numbered the way tree-sitter counts rows.

    Only ``\\n`` ends a line; a trailing ``\\r`` from Windows line endings is
    dropped from each line, and a final newline does not create an extra line.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def build_chunks(
    file_path: str,
    language: str,
    lines: Sequence[str],
    segments: Sequence[Segment],
    header: Sequence[LineRange],
    partial_regions: Sequence[LineRange],
    config: ChunkingConfig,
) -> list[Chunk]:
    """Turn a file's segments into numbered, self-contained chunks.

    Chunks whose body holds only blank lines are dropped.
    """
    chunks: list[Chunk] = []
    for group in pack_segments(segments, config.target_lines):
        body = LineRange(start=group[0].lines.start, end=group[-1].lines.end)
        if not any(lines[number - 1].strip() for number in range(body.start, body.end + 1)):
            continue
        signatures = [signature for segment in group for signature in segment.context]
        context = select_context(body, signatures, header, config.max_context_lines)
        chunks.append(
            Chunk(
                file_path=file_path,
                language=language,
                index=len(chunks),
                lines=body,
                context=context,
                partial_regions=[
                    overlap for region in partial_regions if (overlap := region.intersection(body))
                ],
                numbered_code=render_numbered(lines, [*context, body]),
            )
        )
    return chunks


def pack_segments(segments: Sequence[Segment], target_lines: int) -> list[list[Segment]]:
    """Group consecutive segments while the group spans at most ``target_lines``.

    A single segment larger than the target forms its own group; segments are
    already capped at the maximum chunk size, so no group can exceed it.
    """
    groups: list[list[Segment]] = []
    current: list[Segment] = []
    for segment in segments:
        if current and segment.lines.end - current[0].lines.start + 1 > target_lines:
            groups.append(current)
            current = []
        current.append(segment)
    if current:
        groups.append(current)
    return groups


def select_context(
    body: LineRange,
    signatures: Sequence[LineRange],
    header: Sequence[LineRange],
    max_lines: int,
) -> list[LineRange]:
    """Pick the lines shown above a chunk body.

    Only lines before the body are used, never lines inside it. Enclosing
    signatures come first because they say what the body belongs to; header
    lines such as imports fill the remaining budget.
    """
    candidates = [
        part
        for line_range in (*merge_ranges(signatures), *header)
        for part in line_range.without(body)
        if part.end < body.start
    ]
    selected: list[LineRange] = []
    remaining = max_lines
    for candidate in candidates:
        for part in _without_any(candidate, selected):
            if remaining == 0:
                return merge_ranges(selected)
            taken = LineRange(start=part.start, end=min(part.end, part.start + remaining - 1))
            selected.append(taken)
            remaining -= taken.length
    return merge_ranges(selected)


def render_numbered(lines: Sequence[str], blocks: Sequence[LineRange]) -> str:
    """Render ordered, non-overlapping line blocks as ``<number> | <code>``.

    Numbers are right-aligned to the width of the file's last line number, and
    a gap marker separates blocks that are not adjacent.
    """
    width = len(str(len(lines)))
    rendered: list[str] = []
    previous_end = 0
    for block in blocks:
        if rendered and block.start > previous_end + 1:
            rendered.append(f"{'':>{width}} | {GAP_MARKER}")
        numbers = range(block.start, block.end + 1)
        rendered.extend(f"{number:>{width}} | {lines[number - 1]}" for number in numbers)
        previous_end = block.end
    return "\n".join(rendered)


def _without_any(candidate: LineRange, taken: Sequence[LineRange]) -> list[LineRange]:
    parts = [candidate]
    for existing in taken:
        parts = [piece for part in parts for piece in part.without(existing)]
    return parts
