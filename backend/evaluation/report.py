"""Turn recorded runs into scores and markdown tables.

Only reported findings count, exactly as the product shows them: open,
accepted or needing review, and AI-only findings at or above the confidence
threshold. Rejected findings and those dismissed by AI review do not count.

A configuration is scored on the files it completed, against those files'
labels. A file whose review failed (a quota ran out) would otherwise count as
the model finding nothing.
"""

import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.findings import FindingStatus
from app.llm.models import CallRecord, CallStatus, Task
from app.review.merge import is_reported
from app.review.planner import DEFAULT_MIN_CONFIDENCE
from evaluation.dataset import Dataset
from evaluation.runner import PROVIDER_MODEL_SETTINGS, RUNS_DIR, FileRecord, load_records
from evaluation.scoring import Counts, Prediction, Scorecard, assess, score

RESULTS_DIR = RUNS_DIR.parent
PINNED = ("A", "B-nvidia", "F-nvidia", "E-nvidia+gemini", "E-nvidia+local")
"""The ablation with one reviewer (NVIDIA), review task only."""
ROUTED = ("A", "B", "D", "E")
"""The ablation as routed across every provider, with style review."""
NAMES = {"F-nvidia": "D-nvidia"}
"""F-nvidia is also the hybrid step of the pinned ablation, so it is named for it there."""
DESCRIPTIONS = {
    "A": "Static analysis only",
    "B-nvidia": "LLM only (no static context)",
    "F-nvidia": "Hybrid: static context + LLM review",
    "E-nvidia+gemini": "Hybrid + cross-check by Gemini",
    "E-nvidia+local": "Hybrid + cross-check by the local model",
    "B": "LLM only, routed",
    "D": "Hybrid, routed",
    "E": "Hybrid + cross-check, routed",
}
MODEL_SOURCES = frozenset(PROVIDER_MODEL_SETTINGS) | {"mock"}
"""Finding sources that are models rather than analyzers."""


@dataclass(frozen=True)
class Verification:
    """What cross-model verification decided, and whether it decided right.

    Disputed findings stay reported, flagged for human review, so verification
    changes no score by itself; this shows whether the flags point at the right
    findings.

    Attributes:
        confirmed_real: Confirmed findings that match a labeled issue.
        disputed_false: Disputed findings that match no labeled issue.
        precision_if_hidden: Overall precision had disputed findings been hidden.
    """

    confirmed: int
    confirmed_real: int
    disputed: int
    disputed_false: int
    precision_if_hidden: float | None


@dataclass(frozen=True)
class VariantResult:
    """One configuration's scores and what it cost.

    Attributes:
        scorecard: Scores of every reported finding.
        model_scorecard: Scores of the findings a model reported or confirmed.
        files: Files with a record; ``complete_files`` finished without failures
            and are the ones scored.
        models: Provider name to model id.
        calls: Model call attempts by provider and status.
        latency_ms: Median and 95th percentile of answered calls, per provider.
        file_seconds: Median and 95th percentile time to scan one file.
    """

    variant: str
    run: str
    scorecard: Scorecard
    model_scorecard: Scorecard
    files: int
    complete_files: int
    models: dict[str, str]
    calls: dict[str, dict[str, int]]
    latency_ms: dict[str, tuple[int, int]]
    tokens: tuple[int, int]
    file_seconds: tuple[float, float]
    discarded: int
    tasks_failed: int
    verification: Verification | None = None


def evaluate(dataset: Dataset, runs_dir: Path = RUNS_DIR) -> list[VariantResult]:
    """Score every configuration recorded in ``runs_dir``."""
    results: list[VariantResult] = []
    for path in sorted(runs_dir.glob("*.jsonl")):
        records = [r for name, r in sorted(load_records(path).items()) if name in dataset.files]
        variants = sorted({v for record in records for v in record.variants})
        results.extend(variant_result(dataset, records, variant) for variant in variants)
    return sorted(results, key=lambda result: _order(result.variant))


def variant_result(dataset: Dataset, records: Sequence[FileRecord], variant: str) -> VariantResult:
    """Score one configuration on the files its run completed."""
    complete = [r for r in records if r.complete and variant in r.variants]
    covered = {record.file for record in complete}
    labels = [lb for lb in dataset.labels if lb.label.file in covered]
    clean = [name for name in dataset.clean_files if name in covered]
    reported = [
        finding
        for record in complete
        for finding in record.variants[variant]
        if is_reported(finding, DEFAULT_MIN_CONFIDENCE)
    ]
    predictions = [Prediction.from_finding(finding) for finding in reported]
    correct = assess(predictions, labels).correct
    confirmed = [f for f in reported if f.verified_by]
    # The verifier records a dispute as needs_review with a note saying who disagreed;
    # review's own judgements can also leave a finding needing review, without that note.
    disputed = [
        f
        for f in reported
        if f.status is FindingStatus.NEEDS_REVIEW and " disagreed" in (f.ai_note or "")
    ]
    kept = len(predictions) - len(disputed)
    verification = (
        Verification(
            confirmed=len(confirmed),
            confirmed_real=sum(f.id in correct for f in confirmed),
            disputed=len(disputed),
            disputed_false=sum(f.id not in correct for f in disputed),
            precision_if_hidden=(
                (len(correct) - sum(f.id in correct for f in disputed)) / kept if kept else None
            ),
        )
        if variant == "E" or variant.startswith("E-")
        else None
    )
    by_models = [p for p in predictions if MODEL_SOURCES.intersection(p.sources)]
    calls = [call for record in complete for call in _calls_for(record, variant)]
    totals = [
        sum(record.durations_ms.get(step, 0) for step in _steps(variant)) for record in complete
    ]
    return VariantResult(
        variant=variant,
        run=records[0].run if records else "",
        scorecard=score(predictions, labels, clean),
        model_scorecard=score(by_models, labels, clean),
        files=len(records),
        complete_files=len(complete),
        models=complete[0].models if complete else {},
        calls=_call_counts(calls),
        latency_ms=_latencies(calls),
        tokens=(sum(c.input_tokens for c in calls), sum(c.output_tokens for c in calls)),
        file_seconds=_p50_p95([total / 1000 for total in totals]),
        discarded=sum(record.stats.get("discarded", 0) for record in complete),
        tasks_failed=sum(record.stats.get("tasks_failed", 0) for record in records),
        verification=verification,
    )


def _calls_for(record: FileRecord, variant: str) -> list[CallRecord]:
    # D stops before verification, so its cost leaves out the verify calls E adds.
    return [call for call in record.calls if variant != "D" or call.task is not Task.VERIFY]


def _steps(variant: str) -> tuple[str, ...]:
    return ("static", "review") if variant == "D" else ("static", "review", "verify")


def _call_counts(calls: Iterable[CallRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for call in calls:
        counts[call.provider][call.status.value] += 1
    return {provider: dict(sorted(c.items())) for provider, c in sorted(counts.items())}


def _latencies(calls: Iterable[CallRecord]) -> dict[str, tuple[int, int]]:
    by_provider: dict[str, list[float]] = defaultdict(list)
    for call in calls:
        if call.status is CallStatus.OK:
            by_provider[call.provider].append(call.latency_ms)
    latencies = {}
    for provider, values in sorted(by_provider.items()):
        p50, p95 = _p50_p95(values)
        latencies[provider] = (round(p50), round(p95))
    return latencies


def _p50_p95(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    cuts = statistics.quantiles(values, n=20, method="inclusive")
    return (statistics.median(values), cuts[18])


def _order(variant: str) -> tuple[int, int, str]:
    for group, members in enumerate((PINNED, ROUTED)):
        if variant in members:
            return (group, members.index(variant), variant)
    return (2, 0, variant)


def _pick(results: Sequence[VariantResult], variants: Sequence[str]) -> list[VariantResult]:
    by_variant = {result.variant: result for result in results}
    return [by_variant[variant] for variant in variants if variant in by_variant]


def _name(variant: str, *, pinned: bool = False) -> str:
    return NAMES.get(variant, variant) if pinned else variant


# Rendering ------------------------------------------------------------------


def to_json(results: Sequence[VariantResult]) -> dict[str, Any]:
    """Every result as plain data, with the derived metrics spelled out."""

    def counts(value: Counts) -> dict[str, Any]:
        return {
            **asdict(value),
            "precision": value.precision,
            "recall": value.recall,
            "f1": value.f1,
        }

    out: dict[str, Any] = {}
    for result in results:
        card = result.scorecard
        out[result.variant] = {
            "run": result.run,
            "files": result.files,
            "complete_files": result.complete_files,
            "models": result.models,
            "overall": counts(card.overall),
            "model_findings": counts(result.model_scorecard.overall),
            "location_only": counts(card.location_only),
            "macro_f1": card.macro_f1,
            "by_category": {name: counts(c) for name, c in card.by_category.items()},
            "recall_by_detection": {k: counts(c) for k, c in card.recall_by_detection.items()},
            "recall_by_cwe": {k: counts(c) for k, c in card.recall_by_cwe.items()},
            "clean_file_findings": card.clean_file_findings,
            "found": sorted(card.found),
            "calls": result.calls,
            "latency_ms_p50_p95": result.latency_ms,
            "tokens_in_out": result.tokens,
            "file_seconds_p50_p95": result.file_seconds,
            "discarded": result.discarded,
            "tasks_failed": result.tasks_failed,
            "verification": asdict(result.verification) if result.verification else None,
        }
    return out


def to_markdown(dataset: Dataset, results: Sequence[VariantResult]) -> str:
    """The tables quoted in ``docs/evaluation.md``."""
    pinned = _pick(results, PINNED)
    routed = _pick(results, ROUTED)
    ablations = _pick(results, [*PINNED, *ROUTED[1:]])
    models = [r for r in results if r.variant.startswith("F-")]
    sections = [
        f"Dataset: {dataset.name} v{dataset.version}, {len(dataset.files)} files "
        f"({len(dataset.clean_files)} clean), {len(dataset.labels)} labels.",
        "## Ablation with one reviewer (NVIDIA, review task)\n\n" + _headline(pinned, pinned=True),
        "## Ablation as routed (every provider, review and style)\n\n" + _headline(routed),
        "## Per category (F1, with precision / recall)\n\n" + _categories(ablations),
        "## Security recall per CWE\n\n" + _cwe(dataset, ablations),
        "## Model comparison (review task only, one provider each)\n\n" + _models(models)
        if models
        else "",
        "## Cross-model verification\n\n" + _verification(results),
        "## Cost and routing\n\n" + _cost(results),
        "## Labels found\n\n" + _labels(dataset, results),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"


def pct(value: float | None) -> str:
    """A metric with two decimals, or a dash when it is undefined."""
    return "—" if value is None else f"{value:.2f}"


def _headline(results: Sequence[VariantResult], *, pinned: bool = False) -> str:
    rows = [
        "| Config | Description | Files | Reported | Precision | Recall | F1 | Macro-F1 "
        "| Clean-file FPs | Recall (static-type) | Recall (semantic) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        card = r.scorecard
        static = card.recall_by_detection["static"]
        semantic = card.recall_by_detection["semantic"]
        rows.append(
            f"| {_name(r.variant, pinned=pinned)} "
            f"| {DESCRIPTIONS.get(r.variant, _model_description(r))} "
            f"| {r.complete_files}/{r.files} | {card.overall.predictions} "
            f"| {pct(card.overall.precision)} | {pct(card.overall.recall)} "
            f"| {pct(card.overall.f1)} | {pct(card.macro_f1)} | {card.clean_file_findings} "
            f"| {static.found_labels}/{static.labels} | {semantic.found_labels}/{semantic.labels} |"
        )
    return "\n".join(rows)


def _model_description(result: VariantResult) -> str:
    provider = result.variant.removeprefix("F-")
    return f"Review by {provider} only"


def _models(results: Sequence[VariantResult]) -> str:
    rows = [
        "| Config | Model | Files | Model findings | Precision (model findings) "
        "| Semantic labels found | Recall (with static) | F1 (with static) "
        "| Clean-file FPs (model) | Answered p50 / p95 (ms) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        provider = r.variant.removeprefix("F-")
        mine = r.model_scorecard
        semantic = mine.recall_by_detection["semantic"]
        p50, p95 = r.latency_ms.get(provider, (0, 0))
        rows.append(
            f"| {r.variant} | `{r.models.get(provider, provider)}` "
            f"| {r.complete_files}/{r.files} | {mine.overall.predictions} "
            f"| {pct(mine.overall.precision)} | {semantic.found_labels}/{semantic.labels} "
            f"| {pct(r.scorecard.overall.recall)} | {pct(r.scorecard.overall.f1)} "
            f"| {mine.clean_file_findings} | {p50} / {p95} |"
        )
    return "\n".join(rows)


def _categories(results: Sequence[VariantResult]) -> str:
    categories = sorted({c for r in results for c in r.scorecard.by_category})
    rows = [
        "| Category | " + " | ".join(r.variant for r in results) + " |",
        "|---|" + "---|" * len(results),
    ]
    for category in categories:
        cells = []
        for r in results:
            c = r.scorecard.by_category.get(category)
            cells.append(
                "—"
                if c is None
                else f"{pct(c.f1)} ({pct(c.precision)} / {pct(c.recall)}, n={c.labels})"
            )
        rows.append(f"| {category} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _cwe(dataset: Dataset, results: Sequence[VariantResult]) -> str:
    cwes = sorted({lb.label.cwe for lb in dataset.labels if lb.label.cwe})
    rows = [
        "| CWE | Labels | " + " | ".join(r.variant for r in results) + " |",
        "|---|---|" + "---|" * len(results),
    ]
    for cwe in cwes:
        total = sum(lb.label.cwe == cwe for lb in dataset.labels)
        cells = [_found(r.scorecard.recall_by_cwe.get(cwe)) for r in results]
        rows.append(f"| {cwe} | {total} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _verification(results: Sequence[VariantResult]) -> str:
    rows = [
        "| Config | Confirmed | of them labeled issues | Disputed (flagged for review) "
        "| of them false positives | Precision as reported | Precision if disputed were hidden |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        v = r.verification
        if v is None:
            continue
        rows.append(
            f"| {r.variant} | {v.confirmed} | {v.confirmed_real} | {v.disputed} "
            f"| {v.disputed_false} | {pct(r.scorecard.overall.precision)} "
            f"| {pct(v.precision_if_hidden)} |"
        )
    return "\n".join(rows)


def _found(counts: Counts | None) -> str:
    return "—" if counts is None else f"{counts.found_labels}/{counts.labels}"


def _cost(results: Sequence[VariantResult]) -> str:
    rows = [
        "| Config | Calls (provider: status counts) | Answered-call latency p50 / p95 (ms) "
        "| Tokens in / out | Seconds per file p50 / p95 | Discarded items | Failed tasks |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        calls = "; ".join(
            f"{provider}: " + ", ".join(f"{status} {n}" for status, n in statuses.items())
            for provider, statuses in r.calls.items()
        )
        latency = "; ".join(f"{p}: {a} / {b}" for p, (a, b) in r.latency_ms.items())
        rows.append(
            f"| {r.variant} | {calls or '—'} | {latency or '—'} "
            f"| {r.tokens[0]:,} / {r.tokens[1]:,} "
            f"| {r.file_seconds[0]:.1f} / {r.file_seconds[1]:.1f} | {r.discarded} "
            f"| {r.tasks_failed} |"
        )
    return "\n".join(rows)


def _labels(dataset: Dataset, results: Sequence[VariantResult]) -> str:
    rows = [
        "| Label | Category | Detection | " + " | ".join(r.variant for r in results) + " |",
        "|---|---|---|" + "---|" * len(results),
    ]
    for located in dataset.labels:
        label = located.label
        marks = ["✓" if label.id in r.scorecard.found else "·" for r in results]
        rows.append(
            f"| {label.id} | {label.category.value} | {label.detection} | "
            + " | ".join(marks)
            + " |"
        )
    return "\n".join(rows)


def write(dataset: Dataset, results: Sequence[VariantResult], out_dir: Path = RESULTS_DIR) -> None:
    """Write ``scores.json`` and ``tables.md`` to ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scores.json").write_text(
        json.dumps(to_json(results), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "tables.md").write_text(
        to_markdown(dataset, results), encoding="utf-8", newline="\n"
    )
