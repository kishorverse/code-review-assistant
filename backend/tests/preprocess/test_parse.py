from tree_sitter import Parser

from app.languages.javascript import JAVASCRIPT
from app.languages.python import PYTHON
from app.preprocess.models import LineRange
from app.preprocess.parse import find_partial_regions, node_lines, parse_source


def test_valid_code_has_no_partial_regions() -> None:
    parsed = parse_source(b"def ok():\n    return 1\n", PYTHON)

    assert parsed.partial_regions == []
    assert parsed.tree.root_node.type == "module"


def test_broken_function_is_reported_while_valid_code_around_it_still_parses() -> None:
    source = (
        b"def before():\n"  # 1
        b"    return 1\n"  # 2
        b"\n"  # 3
        b"def broken(:\n"  # 4
        b"    return 2\n"  # 5
        b"\n"  # 6
        b"class After:\n"  # 7
        b"    pass\n"  # 8
    )

    parsed = parse_source(source, PYTHON)

    assert len(parsed.partial_regions) == 1
    region = parsed.partial_regions[0]
    assert region.start == 4
    assert region.end < 7
    top_level = [node.type for node in parsed.tree.root_node.named_children]
    assert top_level[0] == "function_definition"
    assert top_level[-1] == "class_definition"


def test_truncated_code_reports_missing_tokens() -> None:
    parsed = parse_source(b"function f() {\n  if (x) {\n    return 1;\n", JAVASCRIPT)

    assert parsed.partial_regions
    assert parsed.partial_regions[-1].end <= 3


def test_deeply_nested_code_does_not_exhaust_recursion() -> None:
    source = b"x = " + b"[" * 3000 + b"]" * 2999 + b"\n"

    regions = find_partial_regions(parse_source(source, PYTHON).tree.root_node)

    assert regions


def test_node_lines_excludes_the_row_a_trailing_newline_ends_on() -> None:
    tree = Parser(PYTHON.grammar()).parse(b"def f():\n    return 1\n\n\nx = 2\n")
    function, assignment = tree.root_node.named_children

    assert node_lines(function) == LineRange(start=1, end=2)
    assert node_lines(assignment) == LineRange(start=5, end=5)
    assert node_lines(tree.root_node) == LineRange(start=1, end=5)
