"""Labeled datasets: source files and the issues injected into them.

A label names its line by an ``anchor``, text that occurs on exactly one line of
the file, instead of a line number. Editing a dataset file therefore cannot
silently move a label onto the wrong line: loading fails instead.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.findings import Category, Severity

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "eval"
SEEDED_DATASET = EVAL_DIR / "datasets" / "seeded"

Detection = Literal["static", "semantic"]
DETECTIONS: tuple[Detection, ...] = ("static", "semantic")


class DatasetError(Exception):
    """A dataset's labels do not match its files."""


class Label(BaseModel):
    """One injected issue, as written in ``labels.json``.

    Attributes:
        anchor: Text found on exactly one line of the file: the label's first line.
        lines: How many lines the issue spans, starting at the anchor.
        detection: Whether a static analyzer is expected to find the issue, or it
            takes understanding of the code. Decided when the label was written.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    file: str
    anchor: str = Field(min_length=1)
    lines: int = Field(default=1, ge=1)
    category: Category
    cwe: str | None = None
    severity: Severity
    detection: Detection
    description: str


class LabelFile(BaseModel):
    """The contents of ``labels.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: str
    version: int
    description: str
    labels: list[Label]


@dataclass(frozen=True)
class LocatedLabel:
    """A label with the lines its anchor resolved to (1-based, inclusive)."""

    label: Label
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Dataset:
    """Source files and their located labels.

    Attributes:
        source_dir: Directory holding the files, scanned as a project.
        files: POSIX paths of every Python file, relative to ``source_dir``.
    """

    name: str
    version: int
    source_dir: Path
    files: tuple[str, ...]
    labels: tuple[LocatedLabel, ...]

    @property
    def clean_files(self) -> tuple[str, ...]:
        """Files without any label: every finding in them is a false positive."""
        labeled = {entry.label.file for entry in self.labels}
        return tuple(name for name in self.files if name not in labeled)


def load_dataset(directory: Path = SEEDED_DATASET) -> Dataset:
    """Load ``labels.json`` and the ``src/`` files next to it.

    Raises:
        DatasetError: If a label names a missing file, its anchor is not on exactly
            one line, it runs past the end of the file, or two labels share an id.
    """
    spec = LabelFile.model_validate(
        json.loads((directory / "labels.json").read_text(encoding="utf-8"))
    )
    source_dir = directory / "src"
    files = tuple(
        sorted(path.relative_to(source_dir).as_posix() for path in source_dir.rglob("*.py"))
    )
    ids = [label.id for label in spec.labels]
    if duplicates := sorted({label_id for label_id in ids if ids.count(label_id) > 1}):
        raise DatasetError(f"duplicate label ids: {', '.join(duplicates)}")
    texts: dict[str, list[str]] = {}
    located = []
    for label in spec.labels:
        if label.file not in files:
            raise DatasetError(f"{label.id}: no file {label.file}")
        if label.file not in texts:
            texts[label.file] = (source_dir / label.file).read_text(encoding="utf-8").splitlines()
        located.append(locate(label, texts[label.file]))
    return Dataset(
        name=spec.dataset,
        version=spec.version,
        source_dir=source_dir,
        files=files,
        labels=tuple(located),
    )


def locate(label: Label, lines: list[str]) -> LocatedLabel:
    """Resolve a label's anchor to its line numbers in ``lines``."""
    hits = [number for number, text in enumerate(lines, start=1) if label.anchor in text]
    if len(hits) != 1:
        found = "not found" if not hits else f"on lines {hits}"
        raise DatasetError(f"{label.id}: anchor {label.anchor!r} {found}")
    start = hits[0]
    end = start + label.lines - 1
    if end > len(lines):
        raise DatasetError(f"{label.id}: spans past the end of {label.file}")
    return LocatedLabel(label=label, start_line=start, end_line=end)
