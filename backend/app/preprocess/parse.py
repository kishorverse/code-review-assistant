"""Error-tolerant parsing with tree-sitter.

tree-sitter always produces a tree, even for broken or truncated code. The
regions it could not parse are recorded as ``partial_regions`` so later
stages can treat them as incomplete rather than report every truncation as a
syntax error.
"""

from dataclasses import dataclass

from tree_sitter import Node, Parser, Tree

from app.languages.base import LanguageAdapter
from app.preprocess.models import LineRange, merge_ranges


@dataclass(frozen=True)
class ParsedSource:
    """A syntax tree and the lines that failed to parse."""

    tree: Tree
    partial_regions: list[LineRange]


def parse_source(source: bytes, adapter: LanguageAdapter) -> ParsedSource:
    """Parse ``source`` with the adapter's grammar.

    A new parser is created per call because tree-sitter parsers are not
    thread-safe and preprocessing may run in worker threads.
    """
    tree = Parser(adapter.grammar()).parse(source)
    return ParsedSource(tree=tree, partial_regions=find_partial_regions(tree.root_node))


def find_partial_regions(root: Node) -> list[LineRange]:
    """Return merged line ranges covered by ``ERROR`` or ``MISSING`` nodes.

    Only subtrees that contain an error are visited, and the walk is iterative
    so deeply nested code cannot exhaust the recursion limit.
    """
    regions: list[LineRange] = []
    pending = [root]
    while pending:
        node = pending.pop()
        if node.type == "ERROR" or node.is_missing:
            regions.append(node_lines(node))
        elif node.has_error:
            pending.extend(node.children)
    return merge_ranges(regions)


def node_lines(node: Node) -> LineRange:
    """The 1-based lines a node occupies.

    A node whose end point is column 0 of a later row ends with a newline and
    does not actually touch that row, so the row is excluded.
    """
    start_row = node.start_point.row
    end_row = node.end_point.row
    if end_row > start_row and node.end_point.column == 0:
        end_row -= 1
    return LineRange(start=start_row + 1, end=end_row + 1)
