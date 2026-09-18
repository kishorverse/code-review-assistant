import json
from pathlib import Path

import pytest

from evaluation.dataset import SEEDED_DATASET, DatasetError, load_dataset

SOURCE = "import os\n\n\ndef run(cmd):\n    os.system(cmd)\n"


def write_dataset(root: Path, labels: list[dict[str, object]]) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "tool.py").write_text(SOURCE, encoding="utf-8")
    (root / "src" / "clean.py").write_text("X = 1\n", encoding="utf-8")
    spec = {"dataset": "tiny", "version": 1, "description": "test", "labels": labels}
    (root / "labels.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def label(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "tool/shell",
        "file": "tool.py",
        "anchor": "os.system(cmd)",
        "category": "security",
        "cwe": "CWE-78",
        "severity": "high",
        "detection": "static",
        "description": "Shell command from input.",
    }
    return {**base, **changes}


def test_labels_resolve_to_the_line_their_anchor_is_on(tmp_path: Path) -> None:
    dataset = load_dataset(write_dataset(tmp_path, [label(lines=2, anchor="def run")]))

    [located] = dataset.labels
    assert (located.start_line, located.end_line) == (4, 5)
    assert dataset.files == ("clean.py", "tool.py")
    assert dataset.clean_files == ("clean.py",)


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (label(anchor="subprocess"), "not found"),
        (label(anchor="o"), "on lines"),
        (label(file="missing.py"), "no file"),
        (label(lines=3), "past the end"),
    ],
)
def test_labels_that_do_not_fit_their_file_are_rejected(
    tmp_path: Path, bad: dict[str, object], message: str
) -> None:
    with pytest.raises(DatasetError, match=message):
        load_dataset(write_dataset(tmp_path, [bad]))


def test_duplicate_label_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="duplicate"):
        load_dataset(write_dataset(tmp_path, [label(), label()]))


def test_the_seeded_dataset_is_consistent() -> None:
    dataset = load_dataset(SEEDED_DATASET)

    assert len(dataset.labels) >= 50
    assert len(dataset.clean_files) >= 10
    assert all(entry.label.cwe for entry in dataset.labels if entry.label.category == "security")
