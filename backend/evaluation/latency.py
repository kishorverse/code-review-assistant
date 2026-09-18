"""End-to-end latency: synthetic files of 50, 200 and 500 lines, and a whole project.

Each scan runs the full pipeline as the CLI does, with a fresh router so that no
answer comes from the response cache. Static scans show what the analyzers cost;
hybrid scans (standard depth, hosted models allowed) add review, cross-checking
and the summary. Model latency depends on the providers' load at the time, so
the results record when they were measured.
"""

import statistics
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import get_settings
from app.events import NullSink, ScanStage
from app.ingest.storage import ScanStorage, new_scan_id
from app.llm.factory import build_router
from app.pipeline import (
    Ingest,
    ReviewSetup,
    ScanSettings,
    directory_ingest,
    run_scan,
    upload_ingest,
)
from app.review.planner import Depth, ReviewOptions
from app.static.runner import default_analyzers
from evaluation.dataset import SEEDED_DATASET

SIZES = (50, 200, 500)
STAGES = (ScanStage.ANALYZING, ScanStage.REVIEWING, ScanStage.VERIFYING, ScanStage.SUMMARIZING)

_TEMPLATES = (
    '''def total_{n}(values: list[int], limit: int) -> int:
    """Sum the values of batch {n} that stay under ``limit``."""
    total = 0
    for value in values:
        if value < limit:
            total += value * {k}
        elif value == limit:
            total -= {k}
    return total
''',
    '''def label_{n}(name: str, count: int) -> str:
    """A display label for item {n}."""
    if count == 0:
        return f"{{name}}: none"
    suffix = "s" if count > 1 else ""
    return f"{{name}}: {{count}} item{{suffix}} ({k})"
''',
    '''class Counter{n}:
    """Counts events of kind {n}."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {{}}

    def add(self, key: str) -> int:
        """Count ``key`` once more and return its count."""
        self.seen[key] = self.seen.get(key, 0) + {k}
        return self.seen[key]
''',
)


def synthetic_source(lines: int) -> str:
    """Plain, well-formed Python of about ``lines`` lines, the same on every call."""
    parts = ['"""Synthetic module for latency measurements."""\n']
    number = 0
    while sum(part.count("\n") for part in parts) < lines:
        template = _TEMPLATES[number % len(_TEMPLATES)]
        parts.append("\n\n" + template.format(n=number, k=number % 7 + 1))
        number += 1
    return "".join(parts)


@dataclass(frozen=True)
class Measurement:
    """One scan's wall-clock time and where it went."""

    target: str
    mode: str
    seconds: float
    stage_seconds: dict[str, float]
    calls: int
    files: int


async def measure(target: str, mode: str, ingest: Ingest, files: int) -> Measurement:
    """Scan once, as ``static`` or ``hybrid``, and time it."""
    settings = ScanSettings()
    app_settings = get_settings()
    analyzers = default_analyzers(app_settings.opengrep_path)
    with tempfile.TemporaryDirectory(prefix="margin-latency-", ignore_cleanup_errors=True) as temp:
        workspace = ScanStorage(Path(temp)).create(new_scan_id())
        async with httpx.AsyncClient() as client:
            review = None
            if mode == "hybrid":
                options = ReviewOptions(depth=Depth.STANDARD, allow_external=True)
                review = ReviewSetup(build_router(app_settings, client), options)
            started = time.perf_counter()
            result = await run_scan(
                ingest, workspace, NullSink(), settings=settings, analyzers=analyzers, review=review
            )
            seconds = time.perf_counter() - started
    return Measurement(
        target=target,
        mode=mode,
        seconds=round(seconds, 2),
        stage_seconds={
            stage.value: round(result.stage_durations_ms.get(stage, 0) / 1000, 2)
            for stage in STAGES
        },
        calls=len(result.review.calls) if result.review else 0,
        files=files,
    )


async def benchmark(static_runs: int = 5, hybrid_runs: int = 3) -> list[Measurement]:
    """Every size in both modes, then the seeded project once in each mode."""
    measurements: list[Measurement] = []
    settings = ScanSettings()
    with tempfile.TemporaryDirectory(prefix="margin-synthetic-") as temp:
        for size in SIZES:
            path = Path(temp) / f"module_{size}.py"
            path.write_text(synthetic_source(size), encoding="utf-8")
            ingest = upload_ingest(path, path.name, settings.limits)
            for mode, runs in (("static", static_runs), ("hybrid", hybrid_runs)):
                measurements.extend(
                    [await measure(f"{size} lines", mode, ingest, 1) for _ in range(runs)]
                )
    project = SEEDED_DATASET / "src"
    files = len(list(project.rglob("*.py")))
    ingest = directory_ingest(project, settings.limits)
    measurements.extend(
        [
            await measure(f"{files}-file project", mode, ingest, files)
            for mode in ("static", "hybrid")
        ]
    )
    return measurements


def to_markdown(measurements: Sequence[Measurement]) -> str:
    """The latency table quoted in ``docs/evaluation.md``."""
    groups: dict[tuple[str, str], list[Measurement]] = {}
    for measurement in measurements:
        groups.setdefault((measurement.target, measurement.mode), []).append(measurement)
    rows = [
        f"Measured {datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Times in seconds; stage "
        "columns are medians.",
        "",
        "| Input | Mode | Runs | p50 | p95 | Analyzers | Review | Cross-check | Summary "
        "| Model calls | Files per minute |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (target, mode), group in groups.items():
        times = [m.seconds for m in group]
        p50 = statistics.median(times)
        p95 = (
            statistics.quantiles(times, n=20, method="inclusive")[18]
            if len(times) > 1
            else times[0]
        )
        stages = [
            statistics.median(m.stage_seconds[stage.value] for m in group) for stage in STAGES
        ]
        calls = statistics.median(m.calls for m in group)
        per_minute = group[0].files * 60 / p50 if p50 else 0.0
        rows.append(
            f"| {target} | {mode} | {len(group)} | {p50:.1f} | {p95:.1f} | "
            + " | ".join(f"{value:.1f}" for value in stages)
            + f" | {calls:.0f} | {per_minute:.1f} |"
        )
    return "\n".join(rows) + "\n"
