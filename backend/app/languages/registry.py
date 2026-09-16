"""Lookup of language adapters by file extension and shebang interpreter."""

from collections.abc import Callable, Iterable
from pathlib import PurePosixPath

from app.languages.base import LanguageAdapter
from app.languages.go import GO
from app.languages.java import JAVA
from app.languages.javascript import JAVASCRIPT, TSX, TYPESCRIPT
from app.languages.python import PYTHON


class LanguageRegistry:
    """An immutable set of adapters with fast lookup.

    Raises:
        ValueError: If two adapters share a name, an extension or an interpreter,
            which would make detection ambiguous.
    """

    def __init__(self, adapters: Iterable[LanguageAdapter]) -> None:
        self._adapters = tuple(adapters)
        self._by_name = _index(self._adapters, lambda adapter: [adapter.name], "name")
        self._by_extension = _index(
            self._adapters, lambda adapter: sorted(adapter.extensions), "extension"
        )
        self._by_interpreter = _index(
            self._adapters, lambda adapter: sorted(adapter.shebang_interpreters), "interpreter"
        )

    @property
    def adapters(self) -> tuple[LanguageAdapter, ...]:
        """All registered adapters, in registration order."""
        return self._adapters

    def by_name(self, name: str) -> LanguageAdapter | None:
        """Return the adapter with this name, if registered."""
        return self._by_name.get(name)

    def by_extension(self, path: PurePosixPath) -> LanguageAdapter | None:
        """Return the adapter for the file's extension, ignoring case."""
        return self._by_extension.get(path.suffix.lower())

    def by_interpreter(self, interpreter: str) -> LanguageAdapter | None:
        """Return the adapter for a shebang interpreter name such as ``python3``."""
        return self._by_interpreter.get(interpreter)


def _index(
    adapters: tuple[LanguageAdapter, ...],
    keys: Callable[[LanguageAdapter], list[str]],
    label: str,
) -> dict[str, LanguageAdapter]:
    index: dict[str, LanguageAdapter] = {}
    for adapter in adapters:
        for key in keys(adapter):
            if key in index:
                raise ValueError(
                    f"{label} {key!r} is claimed by both {index[key].name} and {adapter.name}"
                )
            index[key] = adapter
    return index


def default_registry() -> LanguageRegistry:
    """The languages Margin supports out of the box."""
    return LanguageRegistry([PYTHON, JAVASCRIPT, TYPESCRIPT, TSX, JAVA, GO])
