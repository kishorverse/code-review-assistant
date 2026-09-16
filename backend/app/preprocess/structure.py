"""Split a parsed file into segments at code boundaries.

Segments cover every line of the file exactly once, in order, and none is
longer than the maximum chunk size.

* The file's top-level statements are the boundaries. Comments directly above
  a statement stay with it; trailing comments stay with the code they follow.
* A statement that is too large is split at the statements inside it: a class
  at its methods, a function at its blocks. The enclosing signature is kept
  as context so each piece still reads correctly on its own.
* Only when no structure is left, or nesting is unreasonably deep, is a region
  cut into fixed-size windows.

Everything language-specific comes from the adapter's declared node types.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tree_sitter import Node

from app.languages.base import LanguageAdapter
from app.preprocess.models import LineRange, merge_ranges
from app.preprocess.parse import node_lines

# Real code rarely nests structure this deep; hostile input can nest thousands of
# levels, so deeper regions fall back to windows instead of recursing further.
MAX_SPLIT_DEPTH = 32


@dataclass(frozen=True)
class Segment:
    """A contiguous run of lines and the signatures that enclose it."""

    lines: LineRange
    context: tuple[LineRange, ...] = ()


@dataclass(frozen=True)
class _Boundary:
    start: int
    node: Node


@dataclass(frozen=True)
class _Region:
    first: int
    last: int
    context: tuple[LineRange, ...]
    depth: int


def header_ranges(root: Node, adapter: LanguageAdapter) -> list[LineRange]:
    """Merged lines of the file's top-level header nodes, such as imports."""
    return merge_ranges(
        node_lines(node) for node in root.named_children if node.type in adapter.header_node_types
    )


def segment_file(
    root: Node, line_count: int, adapter: LanguageAdapter, max_lines: int
) -> list[Segment]:
    """Split a file into contiguous segments of at most ``max_lines`` lines.

    Args:
        root: Root node of the parsed file.
        line_count: Number of lines in the file.
        adapter: Declares which node types are comments and wrappers.
        max_lines: Longest allowed segment.
    """
    if line_count == 0:
        return []
    region = _Region(first=1, last=line_count, context=(), depth=0)
    return _split_region(region, root.named_children, adapter, max_lines)


def _split_region(
    region: _Region, nodes: Sequence[Node], adapter: LanguageAdapter, max_lines: int
) -> list[Segment]:
    boundaries = _boundaries(region, nodes, adapter)
    if not boundaries:
        return _windows(region, max_lines)

    starts = [region.first, *(boundary.start for boundary in boundaries[1:])]
    ends = [*(start - 1 for start in starts[1:]), region.last]
    segments: list[Segment] = []
    for start, end, boundary in zip(starts, ends, boundaries, strict=True):
        piece = _Region(first=start, last=end, context=region.context, depth=region.depth)
        segments.extend(_fit(piece, boundary.node, adapter, max_lines))
    return segments


def _boundaries(
    region: _Region, nodes: Sequence[Node], adapter: LanguageAdapter
) -> list[_Boundary]:
    """Where each statement's segment begins, with leading comments attached."""
    boundaries: list[_Boundary] = []
    covered_until = region.first - 1
    comment_start: int | None = None
    comment_end = 0

    for node in nodes:
        lines = node_lines(node)
        if lines.start > region.last:
            break
        if node.type in adapter.comment_node_types:
            if lines.start <= covered_until:
                continue  # a trailing comment on a line that already has code
            if comment_start is None or lines.start > comment_end + 1:
                comment_start = lines.start  # a blank line starts a new comment block
            comment_end = lines.end
            continue

        start = lines.start
        if comment_start is not None and start <= comment_end + 1:
            start = comment_start
        comment_start = None
        if start > covered_until:
            boundaries.append(_Boundary(start=max(start, region.first), node=node))
        elif boundaries and _spans_further(node, boundaries[-1].node):
            # In `const Foo = () => {...}` the name and the arrow function start on the
            # same line; the arrow function is the part worth splitting further.
            boundaries[-1] = _Boundary(start=boundaries[-1].start, node=node)
        covered_until = max(covered_until, lines.end)
    return boundaries


def _spans_further(candidate: Node, current: Node) -> bool:
    """Whether ``candidate`` starts on the same line as ``current`` but ends later."""
    candidate_lines, current_lines = node_lines(candidate), node_lines(current)
    return candidate_lines.start == current_lines.start and candidate_lines.end > current_lines.end


def _fit(region: _Region, node: Node, adapter: LanguageAdapter, max_lines: int) -> list[Segment]:
    if region.last - region.first + 1 <= max_lines:
        lines = LineRange(start=region.first, end=region.last)
        return [Segment(lines=lines, context=region.context)]
    inner = _inner_structure(node, adapter) if region.depth < MAX_SPLIT_DEPTH else None
    if inner is None:
        return _windows(region, max_lines)
    children, signature = inner
    context = (*region.context, signature) if signature is not None else region.context
    nested = _Region(first=region.first, last=region.last, context=context, depth=region.depth + 1)
    return _split_region(nested, children, adapter, max_lines)


def _inner_structure(
    node: Node, adapter: LanguageAdapter
) -> tuple[list[Node], LineRange | None] | None:
    """The statements to split a large node at, and its signature when it has a body.

    Chains of single-child nodes (an expression wrapping one literal, say) are
    followed down to the first node with several children.
    """
    current = node
    for _ in range(MAX_SPLIT_DEPTH):
        declaration = _unwrap(current, adapter)
        body = declaration.child_by_field_name("body")
        if body is not None and body.named_children:
            return body.named_children, _signature(current, body)
        children = declaration.named_children
        if len(children) != 1:
            return (children, None) if children else None
        current = children[0]
    return None


def _unwrap(node: Node, adapter: LanguageAdapter) -> Node:
    """Follow wrappers such as decorators or exports down to the real declaration."""
    current = node
    for _ in range(MAX_SPLIT_DEPTH):
        inner = next(
            (
                child
                for field in adapter.wrapper_fields
                if (child := current.child_by_field_name(field)) is not None
            ),
            None,
        )
        if inner is None:
            return current
        current = inner
    return current


def _signature(node: Node, body: Node) -> LineRange:
    """Lines from the start of a declaration (including decorators) up to its body."""
    start = node_lines(node).start
    body_start = node_lines(body).start
    return LineRange(start=start, end=body_start - 1 if body_start > start else start)


def _windows(region: _Region, max_lines: int) -> list[Segment]:
    return [
        Segment(
            lines=LineRange(start=start, end=min(start + max_lines - 1, region.last)),
            context=region.context,
        )
        for start in range(region.first, region.last + 1, max_lines)
    ]
