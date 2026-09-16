"""Go: basic support."""

from functools import cache

import tree_sitter_go
from tree_sitter import Language

from app.languages.base import LanguageAdapter, SupportLevel


@cache
def _grammar() -> Language:
    return Language(tree_sitter_go.language())


GO = LanguageAdapter(
    name="go",
    display_name="Go",
    extensions=frozenset({".go"}),
    support=SupportLevel.BASIC,
    style_guide="Effective Go and gofmt conventions",
    grammar=_grammar,
    header_node_types=frozenset({"package_clause", "import_declaration"}),
    comment_node_types=frozenset({"comment"}),
)
