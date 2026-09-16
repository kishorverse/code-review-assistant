"""Java: basic support."""

from functools import cache

import tree_sitter_java
from tree_sitter import Language

from app.languages.base import LanguageAdapter, SupportLevel


@cache
def _grammar() -> Language:
    return Language(tree_sitter_java.language())


JAVA = LanguageAdapter(
    name="java",
    display_name="Java",
    extensions=frozenset({".java"}),
    support=SupportLevel.BASIC,
    style_guide="the Google Java Style Guide",
    grammar=_grammar,
    header_node_types=frozenset({"package_declaration", "import_declaration"}),
    comment_node_types=frozenset({"line_comment", "block_comment"}),
)
