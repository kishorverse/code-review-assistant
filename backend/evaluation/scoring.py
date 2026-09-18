"""Match findings to labels, and compute precision, recall and F1.

A finding matches a label when it is in the same file, its lines overlap the
label's lines give or take ``LINE_TOLERANCE``, and its category agrees. Type
errors count as bugs for matching: a model that calls a type error a bug has
found the same defect.

Precision counts findings that point at any labeled issue, so two analyzers
reporting the same injection are both right. Recall pairs findings with labels
one to one (a maximum bipartite matching), so one finding cannot stand in for
several nearby issues.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.findings import Category, Finding
from evaluation.dataset import DETECTIONS, Detection, LocatedLabel

LINE_TOLERANCE = 2
_SAME_AS = {Category.TYPING: Category.BUG}


@dataclass(frozen=True)
class Prediction:
    """What scoring needs from a finding."""

    id: str
    file: str
    start_line: int
    end_line: int
    category: Category
    sources: tuple[str, ...]

    @classmethod
    def from_finding(cls, finding: Finding) -> "Prediction":
        """The parts of ``finding`` that scoring looks at."""
        return cls(
            id=finding.id,
            file=finding.file_path,
            start_line=finding.start_line,
            end_line=finding.end_line,
            category=finding.category,
            sources=tuple(finding.sources),
        )


def matching_category(category: Category) -> Category:
    """The category used for matching; type errors count as bugs."""
    return _SAME_AS.get(category, category)


def matches(prediction: Prediction, label: LocatedLabel, *, by_category: bool = True) -> bool:
    """Whether ``prediction`` points at the issue ``label`` describes."""
    if prediction.file != label.label.file:
        return False
    if prediction.start_line > label.end_line + LINE_TOLERANCE:
        return False
    if prediction.end_line < label.start_line - LINE_TOLERANCE:
        return False
    if not by_category:
        return True
    return matching_category(prediction.category) is matching_category(label.label.category)


@dataclass(frozen=True)
class Counts:
    """Counts behind precision and recall.

    ``precision`` is ``None`` without predictions and ``recall`` is ``None`` without
    labels: an empty set is neither right nor wrong.
    """

    correct_predictions: int
    predictions: int
    found_labels: int
    labels: int

    @property
    def precision(self) -> float | None:
        """Share of predictions that point at a labeled issue."""
        return self.correct_predictions / self.predictions if self.predictions else None

    @property
    def recall(self) -> float | None:
        """Share of labeled issues that some prediction found."""
        return self.found_labels / self.labels if self.labels else None

    @property
    def f1(self) -> float | None:
        """Harmonic mean of precision and recall."""
        precision, recall = self.precision, self.recall
        if precision is None or recall is None:
            return None
        total = precision + recall
        return 2 * precision * recall / total if total else 0.0


@dataclass(frozen=True)
class Assessment:
    """How a set of predictions fared against a set of labels.

    Attributes:
        found: Ids of labels paired with a prediction.
        correct: Ids of predictions that match at least one label.
    """

    counts: Counts
    found: frozenset[str]
    correct: frozenset[str]


def assess(
    predictions: Sequence[Prediction],
    labels: Sequence[LocatedLabel],
    *,
    by_category: bool = True,
) -> Assessment:
    """Match ``predictions`` against ``labels``."""
    candidates = [
        [
            index
            for index, prediction in enumerate(predictions)
            if matches(prediction, label, by_category=by_category)
        ]
        for label in labels
    ]
    correct = frozenset(
        prediction.id
        for prediction in predictions
        if any(matches(prediction, label, by_category=by_category) for label in labels)
    )
    found = frozenset(labels[index].label.id for index in maximum_matching(candidates))
    return Assessment(
        counts=Counts(
            correct_predictions=sum(p.id in correct for p in predictions),
            predictions=len(predictions),
            found_labels=len(found),
            labels=len(labels),
        ),
        found=found,
        correct=correct,
    )


def maximum_matching(candidates: Sequence[Sequence[int]]) -> dict[int, int]:
    """Pair labels with predictions, one to one, as many as possible.

    Args:
        candidates: For each label, the indexes of the predictions that match it.

    Returns:
        Label index to prediction index, for every label that could be paired.
    """
    owner: dict[int, int] = {}

    def augment(label: int, visited: set[int]) -> bool:
        for prediction in candidates[label]:
            if prediction in visited:
                continue
            visited.add(prediction)
            if prediction not in owner or augment(owner[prediction], visited):
                owner[prediction] = label
                return True
        return False

    for label in range(len(candidates)):
        augment(label, set())
    return {label: prediction for prediction, label in owner.items()}


@dataclass(frozen=True)
class Scorecard:
    """Every metric for one configuration on one dataset.

    Attributes:
        overall: Micro-averaged over all categories.
        location_only: As ``overall``, ignoring categories.
        by_category: Per matching category (type errors count as bugs).
        macro_f1: Mean F1 over the categories that have labels.
        recall_by_detection: Labels found, split by whether static analysis was
            expected to find them.
        recall_by_cwe: Security labels found, per CWE.
        clean_file_findings: Findings reported in files that have no labels.
        found: Ids of the labels that were found.
    """

    overall: Counts
    location_only: Counts
    by_category: dict[str, Counts]
    macro_f1: float | None
    recall_by_detection: dict[Detection, Counts]
    recall_by_cwe: dict[str, Counts]
    clean_file_findings: int
    found: frozenset[str]


def score(
    predictions: Sequence[Prediction],
    labels: Sequence[LocatedLabel],
    clean_files: Iterable[str],
) -> Scorecard:
    """Score one configuration's reported findings against the labels."""
    overall = assess(predictions, labels)
    categories = sorted(
        {matching_category(label.label.category) for label in labels}
        | {matching_category(prediction.category) for prediction in predictions}
    )
    by_category = {
        category.value: assess(
            [p for p in predictions if matching_category(p.category) is category],
            [lb for lb in labels if matching_category(lb.label.category) is category],
        ).counts
        for category in categories
    }
    labeled_f1 = [
        counts.f1 for counts in by_category.values() if counts.labels and counts.f1 is not None
    ]
    clean = set(clean_files)
    return Scorecard(
        overall=overall.counts,
        location_only=assess(predictions, labels, by_category=False).counts,
        by_category=by_category,
        macro_f1=sum(labeled_f1) / len(labeled_f1) if labeled_f1 else None,
        recall_by_detection={
            detection: _recall([lb for lb in labels if lb.label.detection == detection], overall)
            for detection in DETECTIONS
        },
        recall_by_cwe={
            cwe: _recall([lb for lb in labels if lb.label.cwe == cwe], overall)
            for cwe in sorted({lb.label.cwe for lb in labels if lb.label.cwe})
        },
        clean_file_findings=sum(p.file in clean for p in predictions),
        found=overall.found,
    )


def _recall(chosen: Sequence[LocatedLabel], overall: Assessment) -> Counts:
    return Counts(
        correct_predictions=0,
        predictions=0,
        found_labels=sum(label.label.id in overall.found for label in chosen),
        labels=len(chosen),
    )
