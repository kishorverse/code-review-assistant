"""Human ratings of AI suggestions: a blind sample to rate, and how far raters agree.

``sample`` picks AI findings from one configuration and writes a rating sheet
without the provider's name, so raters judge the suggestion, not the model; a
separate key file maps each item back. Raters fill in a copy each
(``ratings_<name>.csv``), scoring correctness, usefulness and clarity from 1 to 5.
``summarize`` reports mean and standard deviation per criterion and per model,
quadratic-weighted Cohen's kappa for every pair of raters, and Fleiss' kappa
when three or more rated the same items.
"""

import csv
import json
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from app.findings import Finding
from app.review.merge import is_reported
from app.review.planner import DEFAULT_MIN_CONFIDENCE
from evaluation.dataset import EVAL_DIR
from evaluation.report import MODEL_SOURCES
from evaluation.runner import FileRecord

HUMAN_EVAL_DIR = EVAL_DIR / "human_eval"
CRITERIA = ("correctness", "usefulness", "clarity")
SCALE = (1, 2, 3, 4, 5)
SHEET_COLUMNS = ("item", "file", "lines", "category", "title", "message", "suggestion", *CRITERIA)


def cohen_kappa(
    first: Sequence[int], second: Sequence[int], categories: Sequence[int], *, quadratic: bool
) -> float:
    """Agreement between two raters beyond chance; quadratic weights suit ordinal scales."""
    if len(first) != len(second) or not first:
        raise ValueError("both raters must rate the same, non-empty set of items")
    index = {category: position for position, category in enumerate(categories)}
    size, total = len(categories), len(first)
    observed = [[0.0] * size for _ in categories]
    for a, b in zip(first, second, strict=True):
        observed[index[a]][index[b]] += 1
    rows = [sum(row) for row in observed]
    columns = [sum(observed[i][j] for i in range(size)) for j in range(size)]

    def weight(i: int, j: int) -> float:
        if quadratic:
            return (i - j) ** 2 / (size - 1) ** 2
        return 0.0 if i == j else 1.0

    disagreement = sum(weight(i, j) * observed[i][j] for i in range(size) for j in range(size))
    expected = sum(
        weight(i, j) * rows[i] * columns[j] / total for i in range(size) for j in range(size)
    )
    return 1.0 if expected == 0 else 1.0 - disagreement / expected


def fleiss_kappa(counts: Sequence[Sequence[int]]) -> float:
    """Agreement among a fixed number of raters per item.

    Args:
        counts: For each item, how many raters chose each category.
    """
    raters = sum(counts[0])
    if raters < 2 or any(sum(row) != raters for row in counts):
        raise ValueError("every item needs the same number of raters, at least two")
    items = len(counts)
    shares = [sum(row[j] for row in counts) / (items * raters) for j in range(len(counts[0]))]
    per_item = [(sum(n * n for n in row) - raters) / (raters * (raters - 1)) for row in counts]
    observed = sum(per_item) / items
    chance = sum(share * share for share in shares)
    return 1.0 if chance == 1 else (observed - chance) / (1 - chance)


@dataclass(frozen=True)
class SampledItem:
    """One finding on the rating sheet, and whom it came from (kept off the sheet)."""

    item: str
    finding: Finding
    providers: tuple[str, ...]


def sample(records: Sequence[FileRecord], variant: str, size: int, seed: int) -> list[SampledItem]:
    """Pick reported findings that a model wrote, with a suggestion to judge."""
    candidates = [
        finding
        for record in records
        if record.complete
        for finding in record.variants.get(variant, [])
        if is_reported(finding, DEFAULT_MIN_CONFIDENCE)
        and finding.suggestion
        and MODEL_SOURCES.intersection(finding.sources)
    ]
    # A seeded, reproducible sample; nothing here needs unpredictability.
    chosen = random.Random(seed).sample(candidates, min(size, len(candidates)))  # noqa: S311
    return [
        SampledItem(
            item=f"S{number:02d}",
            finding=finding,
            providers=tuple(s for s in finding.sources if s in MODEL_SOURCES),
        )
        for number, finding in enumerate(chosen, start=1)
    ]


def write_sheet(items: Sequence[SampledItem], directory: Path = HUMAN_EVAL_DIR) -> None:
    """Write the blank rating sheet and, separately, the key to its items."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "rating_sheet.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(SHEET_COLUMNS)
        for entry in items:
            finding = entry.finding
            writer.writerow(
                [
                    entry.item,
                    finding.file_path,
                    f"{finding.start_line}-{finding.end_line}",
                    finding.category.value,
                    finding.title,
                    finding.message,
                    finding.suggestion,
                    "",
                    "",
                    "",
                ]
            )
    key = {
        entry.item: {"finding": entry.finding.id, "providers": list(entry.providers)}
        for entry in items
    }
    (directory / "sample_key.json").write_text(
        json.dumps(key, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def read_ratings(path: Path) -> dict[str, dict[str, int]]:
    """One rater's scores: item to criterion to score; unrated items are left out."""
    ratings: dict[str, dict[str, int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if all(row.get(criterion, "").strip() for criterion in CRITERIA):
                scores = {criterion: int(row[criterion]) for criterion in CRITERIA}
                if any(score not in SCALE for score in scores.values()):
                    raise ValueError(f"{path.name}, {row['item']}: scores run from 1 to 5")
                ratings[row["item"]] = scores
    return ratings


def summarize(directory: Path = HUMAN_EVAL_DIR) -> str:
    """Markdown summary of every ``ratings_*.csv`` in ``directory``."""
    raters = {
        path.stem.removeprefix("ratings_"): read_ratings(path)
        for path in sorted(directory.glob("ratings_*.csv"))
    }
    if not raters:
        return "No ratings yet: copy rating_sheet.csv to ratings_<name>.csv and fill it in.\n"
    key = json.loads((directory / "sample_key.json").read_text(encoding="utf-8"))
    lines = [f"Raters: {len(raters)} ({', '.join(raters)}).", ""]
    lines += _means(raters, key)
    lines += ["", *_agreement(raters)]
    return "\n".join(lines) + "\n"


def _means(
    raters: dict[str, dict[str, dict[str, int]]], key: dict[str, dict[str, list[str]]]
) -> list[str]:
    rows = [
        "| Group | Items | " + " | ".join(CRITERIA) + " |",
        "|---|---|" + "---|" * len(CRITERIA),
    ]
    providers = sorted({p for entry in key.values() for p in entry["providers"]})
    for group in ["all", *providers]:
        scored = [
            scores
            for ratings in raters.values()
            for item, scores in ratings.items()
            if group == "all" or group in key[item]["providers"]
        ]
        if not scored:
            continue
        cells = []
        for criterion in CRITERIA:
            values = [scores[criterion] for scores in scored]
            spread = statistics.stdev(values) if len(values) > 1 else 0.0
            cells.append(f"{statistics.mean(values):.2f} ± {spread:.2f}")
        items = len(
            {
                item
                for ratings in raters.values()
                for item in ratings
                if group == "all" or group in key[item]["providers"]
            }
        )
        rows.append(f"| {group} | {items} | " + " | ".join(cells) + " |")
    return rows


def _agreement(raters: dict[str, dict[str, dict[str, int]]]) -> list[str]:
    rows = [
        "| Raters | Items | " + " | ".join(CRITERIA) + " |",
        "|---|---|" + "---|" * len(CRITERIA),
    ]
    for (name_a, a), (name_b, b) in combinations(raters.items(), 2):
        shared = sorted(a.keys() & b.keys())
        if len(shared) < 2:
            continue
        cells = [
            _kappa([a[item][criterion] for item in shared], [b[item][criterion] for item in shared])
            for criterion in CRITERIA
        ]
        rows.append(
            f"| {name_a} / {name_b} (weighted Cohen) | {len(shared)} | " + " | ".join(cells) + " |"
        )
    if len(raters) >= 3:
        shared = sorted(set.intersection(*(set(r) for r in raters.values())))
        if len(shared) >= 2:
            cells = []
            for criterion in CRITERIA:
                counts = [
                    [sum(r[item][criterion] == score for r in raters.values()) for score in SCALE]
                    for item in shared
                ]
                cells.append(f"{fleiss_kappa(counts):.2f}")
            rows.append(f"| all (Fleiss) | {len(shared)} | " + " | ".join(cells) + " |")
    return rows


def _kappa(first: Sequence[int], second: Sequence[int]) -> str:
    return f"{cohen_kappa(first, second, SCALE, quadratic=True):.2f}"
