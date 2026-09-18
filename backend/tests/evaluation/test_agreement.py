import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.findings import Category, Finding, Severity
from evaluation.agreement import (
    CRITERIA,
    SHEET_COLUMNS,
    cohen_kappa,
    fleiss_kappa,
    read_ratings,
    sample,
    summarize,
    write_sheet,
)
from evaluation.runner import FileRecord


def test_cohen_kappa_matches_the_textbook_example() -> None:
    # 50 items: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no; kappa = 0.4.
    first = [1] * 25 + [0] * 25
    second = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15

    assert cohen_kappa(first, second, (0, 1), quadratic=False) == pytest.approx(0.4)


def test_weighted_kappa_is_perfect_for_identical_ratings_and_penalizes_distance() -> None:
    ratings = [1, 2, 3, 4, 5, 3]
    near = [1, 2, 3, 4, 4, 3]
    far = [5, 2, 3, 4, 1, 3]

    assert cohen_kappa(ratings, ratings, (1, 2, 3, 4, 5), quadratic=True) == pytest.approx(1.0)
    near_kappa = cohen_kappa(ratings, near, (1, 2, 3, 4, 5), quadratic=True)
    far_kappa = cohen_kappa(ratings, far, (1, 2, 3, 4, 5), quadratic=True)
    assert far_kappa < near_kappa < 1


def test_fleiss_kappa_matches_the_published_example() -> None:
    # Fleiss (1971) as worked on Wikipedia: 10 items, 14 raters, 5 categories.
    counts = [
        [0, 0, 0, 0, 14],
        [0, 2, 6, 4, 2],
        [0, 0, 3, 5, 6],
        [0, 3, 9, 2, 0],
        [2, 2, 8, 1, 1],
        [7, 7, 0, 0, 0],
        [3, 2, 6, 3, 0],
        [2, 5, 3, 2, 2],
        [6, 5, 2, 1, 0],
        [0, 2, 2, 3, 7],
    ]

    assert fleiss_kappa(counts) == pytest.approx(0.210, abs=0.001)


def test_fleiss_kappa_needs_the_same_raters_for_every_item() -> None:
    with pytest.raises(ValueError, match="same number"):
        fleiss_kappa([[1, 1], [2, 1]])


def write_ratings(path: Path, rows: dict[str, tuple[int, int, int]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        for item, scores in rows.items():
            writer.writerow({"item": item, **dict(zip(CRITERIA, scores, strict=True))})


def test_ratings_skip_unrated_items_and_reject_scores_off_the_scale(tmp_path: Path) -> None:
    path = tmp_path / "ratings_a.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerow({"item": "S01", "correctness": 4, "usefulness": 3, "clarity": 5})
        writer.writerow({"item": "S02"})

    assert read_ratings(path) == {"S01": {"correctness": 4, "usefulness": 3, "clarity": 5}}

    write_ratings(path, {"S01": (6, 1, 1)})
    with pytest.raises(ValueError, match="1 to 5"):
        read_ratings(path)


def test_summary_reports_means_per_model_and_agreement(tmp_path: Path) -> None:
    key = {
        "S01": {"finding": "f1", "providers": ["nvidia"]},
        "S02": {"finding": "f2", "providers": ["gemini"]},
        "S03": {"finding": "f3", "providers": ["nvidia"]},
    }
    (tmp_path / "sample_key.json").write_text(json.dumps(key), encoding="utf-8")
    write_ratings(
        tmp_path / "ratings_ana.csv", {"S01": (5, 4, 4), "S02": (2, 2, 3), "S03": (4, 4, 5)}
    )
    write_ratings(
        tmp_path / "ratings_ben.csv", {"S01": (5, 5, 4), "S02": (1, 2, 3), "S03": (4, 3, 5)}
    )

    text = summarize(tmp_path)

    assert "Raters: 2 (ana, ben)." in text
    assert "| nvidia | 2 |" in text
    assert "ana / ben (weighted Cohen) | 3 |" in text


def test_summary_explains_how_to_start_without_ratings(tmp_path: Path) -> None:
    assert "copy rating_sheet.csv" in summarize(tmp_path)


def model_record(variant: str, provider: str, count: int) -> FileRecord:
    findings = [
        Finding(
            file_path="a.py",
            start_line=line,
            end_line=line,
            category=Category.PERFORMANCE,
            severity=Severity.MEDIUM,
            title=f"Slow loop {line}",
            message="Quadratic.",
            suggestion="Use a set.",
            sources=[provider],
            confidence=0.9,
        )
        for line in range(1, count + 1)
    ]
    return FileRecord(
        run=f"model-{provider}",
        file="a.py",
        started_at=datetime(2026, 9, 18, tzinfo=UTC),
        complete=True,
        variants={variant: findings},
        calls=[],
        stats={},
        durations_ms={},
        models={},
        prompt_versions={},
    )


def test_the_sample_is_even_per_model_and_the_sheet_never_names_one(tmp_path: Path) -> None:
    configurations = {
        "F-gemini": [model_record("F-gemini", "gemini", 10)],
        "F-nvidia": [model_record("F-nvidia", "nvidia", 3)],
    }

    items = sample(configurations, size=8, seed=1)
    write_sheet(items, tmp_path)

    providers = [item.providers for item in items]
    assert (providers.count(("gemini",)), providers.count(("nvidia",))) == (4, 3)
    assert [item.item for item in items] == [f"S{n:02d}" for n in range(1, 8)]
    sheet = (tmp_path / "rating_sheet.csv").read_text(encoding="utf-8")
    assert "gemini" not in sheet
    assert "nvidia" not in sheet
    key = json.loads((tmp_path / "sample_key.json").read_text(encoding="utf-8"))
    assert {entry["providers"][0] for entry in key.values()} == {"gemini", "nvidia"}
