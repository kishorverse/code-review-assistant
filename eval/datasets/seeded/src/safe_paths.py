"""Resolve user-supplied names to files inside a storage folder."""

from pathlib import Path


class OutsideStorageError(ValueError):
    """A requested name points outside the storage folder."""


def resolve_inside(storage: Path, name: str) -> Path:
    """The file ``name`` refers to, which must lie inside ``storage``.

    Symbolic links and ``..`` segments are resolved before the check,
    so neither can lead outside the folder.
    """
    root = storage.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise OutsideStorageError(name)
    return candidate
