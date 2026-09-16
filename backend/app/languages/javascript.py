"""JavaScript and TypeScript (including JSX and TSX): basic support."""

from functools import cache

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language

from app.languages.base import LanguageAdapter, SupportLevel

_HEADER_NODE_TYPES = frozenset({"import_statement"})
_COMMENT_NODE_TYPES = frozenset({"comment"})
_WRAPPER_FIELDS = ("declaration",)


@cache
def _javascript_grammar() -> Language:
    return Language(tree_sitter_javascript.language())


@cache
def _typescript_grammar() -> Language:
    return Language(tree_sitter_typescript.language_typescript())


@cache
def _tsx_grammar() -> Language:
    return Language(tree_sitter_typescript.language_tsx())


JAVASCRIPT = LanguageAdapter(
    name="javascript",
    display_name="JavaScript",
    extensions=frozenset({".js", ".jsx", ".mjs", ".cjs"}),
    support=SupportLevel.BASIC,
    style_guide="common JavaScript conventions (Airbnb style guide)",
    grammar=_javascript_grammar,
    header_node_types=_HEADER_NODE_TYPES,
    comment_node_types=_COMMENT_NODE_TYPES,
    wrapper_fields=_WRAPPER_FIELDS,
    shebang_interpreters=frozenset({"node"}),
)

TYPESCRIPT = LanguageAdapter(
    name="typescript",
    display_name="TypeScript",
    extensions=frozenset({".ts", ".mts", ".cts"}),
    support=SupportLevel.BASIC,
    style_guide="common TypeScript conventions (Google TypeScript style guide)",
    grammar=_typescript_grammar,
    header_node_types=_HEADER_NODE_TYPES,
    comment_node_types=_COMMENT_NODE_TYPES,
    wrapper_fields=_WRAPPER_FIELDS,
)

TSX = LanguageAdapter(
    name="tsx",
    display_name="TypeScript (TSX)",
    extensions=frozenset({".tsx"}),
    support=SupportLevel.BASIC,
    style_guide="common TypeScript and React conventions",
    grammar=_tsx_grammar,
    header_node_types=_HEADER_NODE_TYPES,
    comment_node_types=_COMMENT_NODE_TYPES,
    wrapper_fields=_WRAPPER_FIELDS,
)
