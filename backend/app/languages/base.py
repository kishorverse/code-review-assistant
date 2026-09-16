"""The language adapter contract.

An adapter is declarative: it names the tree-sitter grammar, the file
extensions, and which syntax node types play structural roles. The
preprocessing code interprets those declarations generically, so no module
outside ``app/languages`` branches on a language name.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from tree_sitter import Language


class SupportLevel(StrEnum):
    """How much of the review pipeline a language receives."""

    FULL = "full"
    """Every analyzer plus LLM review."""

    BASIC = "basic"
    """Language-agnostic analyzers plus LLM review."""


@dataclass(frozen=True)
class LanguageAdapter:
    """Everything the pipeline needs to know about one language.

    Attributes:
        name: Stable identifier used in findings and reports, e.g. ``"python"``.
        display_name: Human-readable name, e.g. ``"Python"``.
        extensions: Lower-case file extensions including the dot.
        support: Which analyzers apply.
        style_guide: The style reference LLM style review is asked to follow.
        grammar: Returns the tree-sitter grammar; implementations should cache it.
        header_node_types: Top-level nodes that give a chunk its context, such as imports.
        comment_node_types: Comment nodes, which stay attached to the code below them.
        wrapper_fields: Fields that hold the real declaration inside a wrapper node,
            such as a decorated definition or an export statement.
        shebang_interpreters: Interpreter names that identify extension-less scripts.
    """

    name: str
    display_name: str
    extensions: frozenset[str]
    support: SupportLevel
    style_guide: str
    grammar: Callable[[], Language]
    header_node_types: frozenset[str]
    comment_node_types: frozenset[str]
    wrapper_fields: tuple[str, ...] = ()
    shebang_interpreters: frozenset[str] = frozenset()
