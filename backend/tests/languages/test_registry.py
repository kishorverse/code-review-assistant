from dataclasses import replace
from pathlib import PurePosixPath

import pytest
from tree_sitter import Parser

from app.languages.base import LanguageAdapter, SupportLevel
from app.languages.python import PYTHON
from app.languages.registry import LanguageRegistry, default_registry

REGISTRY = default_registry()

VALID_SNIPPETS = {
    "python": b"import os\n\ndef main():\n    return os.getcwd()\n",
    "javascript": b"import fs from 'fs';\nexport function main() { return fs; }\n",
    "typescript": b"import { a } from 'a';\nexport class C { m(): number { return 1; } }\n",
    "tsx": b"export const App = () => <div>Hello</div>;\n",
    "java": b"package demo;\nimport java.util.List;\nclass A { void m() {} }\n",
    "go": b'package main\nimport "fmt"\nfunc main() { fmt.Println("hi") }\n',
}


@pytest.mark.parametrize(
    ("filename", "language"),
    [
        ("app/main.py", "python"),
        ("scripts/tool.PYW", "python"),
        ("web/index.js", "javascript"),
        ("web/App.jsx", "javascript"),
        ("web/config.mjs", "javascript"),
        ("src/api.ts", "typescript"),
        ("src/types.d.ts", "typescript"),
        ("src/App.tsx", "tsx"),
        ("src/Main.java", "java"),
        ("cmd/server.go", "go"),
    ],
)
def test_resolves_supported_extensions_case_insensitively(filename: str, language: str) -> None:
    adapter = REGISTRY.by_extension(PurePosixPath(filename))

    assert adapter is not None
    assert adapter.name == language


@pytest.mark.parametrize("filename", ["README.md", "config.yaml", "Makefile", "data.json"])
def test_returns_none_for_unsupported_files(filename: str) -> None:
    assert REGISTRY.by_extension(PurePosixPath(filename)) is None


def test_resolves_shebang_interpreters() -> None:
    assert REGISTRY.by_interpreter("python3") is PYTHON
    assert REGISTRY.by_interpreter("ruby") is None


def test_python_is_the_only_fully_supported_language() -> None:
    full = [adapter.name for adapter in REGISTRY.adapters if adapter.support is SupportLevel.FULL]

    assert full == ["python"]


@pytest.mark.parametrize("adapter", REGISTRY.adapters, ids=lambda adapter: adapter.name)
def test_grammar_parses_valid_code_without_errors(adapter: LanguageAdapter) -> None:
    tree = Parser(adapter.grammar()).parse(VALID_SNIPPETS[adapter.name])

    assert not tree.root_node.has_error
    assert adapter.grammar() is adapter.grammar()


@pytest.mark.parametrize("adapter", REGISTRY.adapters, ids=lambda adapter: adapter.name)
def test_declared_node_types_and_fields_exist_in_the_grammar(adapter: LanguageAdapter) -> None:
    grammar = adapter.grammar()

    for node_type in adapter.header_node_types | adapter.comment_node_types:
        assert grammar.id_for_node_kind(node_type, True) is not None, node_type
    for field in adapter.wrapper_fields:
        assert grammar.field_id_for_name(field) is not None, field


def test_rejects_adapters_that_claim_the_same_extension() -> None:
    impostor = replace(PYTHON, name="impostor", shebang_interpreters=frozenset())

    with pytest.raises(ValueError, match=r"'\.py' is claimed by both python and impostor"):
        LanguageRegistry([PYTHON, impostor])
