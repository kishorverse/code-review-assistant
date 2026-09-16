"""Python: the fully supported language."""

from functools import cache

import tree_sitter_python
from tree_sitter import Language

from app.languages.base import LanguageAdapter, SupportLevel


@cache
def _grammar() -> Language:
    return Language(tree_sitter_python.language())


PYTHON = LanguageAdapter(
    name="python",
    display_name="Python",
    extensions=frozenset({".py", ".pyw"}),
    support=SupportLevel.FULL,
    style_guide="PEP 8 and PEP 257",
    grammar=_grammar,
    header_node_types=frozenset(
        {"import_statement", "import_from_statement", "future_import_statement"}
    ),
    comment_node_types=frozenset({"comment"}),
    wrapper_fields=("definition",),
    shebang_interpreters=frozenset({"python", "python3"}),
)
