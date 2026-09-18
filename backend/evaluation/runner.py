"""Run ablation configurations over a dataset and record what they found.

Each file is scanned on its own, as a single-file upload, and its record is
appended to a JSON Lines file as soon as it is ready. A run that stops (a free
quota runs out, the machine sleeps) resumes where it left off: files whose
review did not complete are tried again, and the newest record for a file wins.

Runs and the configurations they produce:

- ``static``: A, static analysis only.
- ``llm-only``: B, models review the code without static findings as context.
- ``hybrid``: D, models review with static context; E, D plus cross-model
  verification of high and critical AI findings. Both come from the same review
  calls, so the difference between them is the verifier alone.
- ``model-<provider>``: F, the review task of D with a single provider, for
  comparing models. Style review is left out to fit free-tier quotas.
"""

import asyncio
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.events import NullSink
from app.findings import Finding
from app.ingest.storage import ScanStorage, new_scan_id
from app.llm.factory import build_router
from app.llm.models import CallRecord
from app.llm.router import Router
from app.pipeline import ScanSettings, run_scan, upload_ingest
from app.review.planner import Depth, ReviewOptions
from app.review.session import ReviewSession
from app.static.base import Analyzer
from app.static.runner import default_analyzers
from evaluation.dataset import EVAL_DIR, Dataset

RUNS_DIR = EVAL_DIR / "results" / "runs"
PROVIDER_MODEL_SETTINGS = {
    "gemini": "gemini_model",
    "nvidia": "nvidia_model",
    "hf-large": "hf_model_large",
    "hf-small": "hf_model_small",
    "local": "local_model",
}
"""The setting holding each provider's model id; clearing it disables the provider."""


class RunKind(StrEnum):
    """What a run exercises."""

    STATIC = "static"
    LLM_ONLY = "llm-only"
    HYBRID = "hybrid"
    MODEL = "model"


@dataclass(frozen=True)
class RunSpec:
    """One run over a dataset.

    Attributes:
        provider: For ``model`` runs, the only provider the router may use.
    """

    kind: RunKind
    provider: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is RunKind.MODEL) != (self.provider is not None):
            raise ValueError("a provider is required for model runs, and only for them")
        if self.provider is not None and self.provider not in PROVIDER_MODEL_SETTINGS:
            raise ValueError(f"unknown provider {self.provider}")

    @property
    def name(self) -> str:
        """File-name friendly run name."""
        return f"model-{self.provider}" if self.provider else self.kind.value

    @property
    def variants(self) -> tuple[str, ...]:
        """The configurations this run records."""
        if self.kind is RunKind.STATIC:
            return ("A",)
        if self.kind is RunKind.LLM_ONLY:
            return ("B",)
        if self.kind is RunKind.HYBRID:
            return ("D", "E")
        return (f"F-{self.provider}",)


class FileRecord(BaseModel):
    """What one run did with one file.

    Attributes:
        variants: Every finding each configuration ended with, reported or not.
        complete: False if scanning failed or a review task found no provider;
            such files are run again on resume.
        durations_ms: Wall-clock time of the static, review and verify steps.
        models: Provider name to model id, as configured for the run.
    """

    model_config = ConfigDict(frozen=True)

    run: str
    file: str
    started_at: datetime
    complete: bool
    variants: dict[str, list[Finding]]
    calls: list[CallRecord]
    stats: dict[str, int]
    durations_ms: dict[str, int]
    models: dict[str, str]
    prompt_versions: dict[str, str]
    error: str | None = None


def run_settings(spec: RunSpec, base: Settings) -> Settings:
    """Settings with every provider but the run's own disabled, for model runs."""
    if spec.provider is None:
        return base
    disabled = {
        setting: None for name, setting in PROVIDER_MODEL_SETTINGS.items() if name != spec.provider
    }
    return base.model_copy(update=disabled)


def records_path(spec: RunSpec, runs_dir: Path = RUNS_DIR) -> Path:
    """Where a run's records are kept."""
    return runs_dir / f"{spec.name}.jsonl"


def load_records(path: Path) -> dict[str, FileRecord]:
    """The newest record for each file in a run's records."""
    if not path.exists():
        return {}
    newest: dict[str, FileRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = FileRecord.model_validate_json(line)
            newest[record.file] = record
    return newest


async def run(
    spec: RunSpec,
    dataset: Dataset,
    *,
    files: Sequence[str] | None = None,
    concurrency: int = 4,
    fresh: bool = False,
    rounds: int = 1,
    wait_seconds: float = 65.0,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, FileRecord]:
    """Run ``spec`` over the dataset's files, skipping files already complete.

    Args:
        files: A subset of the dataset's files; all of them by default.
        concurrency: Files scanned at once. Model calls are still limited by the router.
        fresh: Discard earlier records of this run instead of resuming.
        rounds: Passes over the files still incomplete. A single-provider run has
            no fallback, so it needs several to wait out rate-limit pauses.
        wait_seconds: Pause between passes.

    Returns:
        The newest record of every file in the run.
    """
    path = records_path(spec, runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fresh:
        path.unlink(missing_ok=True)
    wanted = list(files or dataset.files)
    for number in range(rounds):
        if number:
            await asyncio.sleep(wait_seconds)
        batch = await _run_pass(spec, dataset, wanted, concurrency, path)
        if all(record.complete for record in batch):
            break
    return {name: record for name, record in load_records(path).items() if name in wanted}


async def _run_pass(
    spec: RunSpec, dataset: Dataset, files: Sequence[str], concurrency: int, path: Path
) -> list[FileRecord]:
    """Scan the files not yet complete, with a fresh router."""
    done = {name for name, record in load_records(path).items() if record.complete}
    pending = [name for name in files if name not in done]
    if not pending:
        return []
    settings = run_settings(spec, get_settings())
    analyzers = default_analyzers(settings.opengrep_path)
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()

    async with httpx.AsyncClient() as client:
        router = None if spec.kind is RunKind.STATIC else build_router(settings, client)

        async def one(name: str) -> FileRecord:
            async with semaphore:
                record = await scan_file(spec, dataset, name, router, analyzers)
            async with lock:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(record.model_dump_json() + "\n")
            return record

        return list(await asyncio.gather(*(one(name) for name in pending)))


async def scan_file(
    spec: RunSpec,
    dataset: Dataset,
    name: str,
    router: Router | None,
    analyzers: list[Analyzer],
) -> FileRecord:
    """Scan one dataset file as ``spec`` says; failures are recorded, not raised."""
    started_at = datetime.now(UTC)
    models = {status.name: status.model for status in router.status()} if router else {}
    try:
        return await _scan(spec, dataset, name, router, analyzers, started_at, models)
    except Exception as error:  # one broken file must not end the run
        return FileRecord(
            run=spec.name,
            file=name,
            started_at=started_at,
            complete=False,
            variants={},
            calls=[],
            stats={},
            durations_ms={},
            models=models,
            prompt_versions={},
            error=f"{type(error).__name__}: {error}",
        )


async def _scan(
    spec: RunSpec,
    dataset: Dataset,
    name: str,
    router: Router | None,
    analyzers: list[Analyzer],
    started_at: datetime,
    models: dict[str, str],
) -> FileRecord:
    settings = ScanSettings()
    durations: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="margin-eval-", ignore_cleanup_errors=True) as temp:
        workspace = ScanStorage(Path(temp)).create(new_scan_id())
        ingest = upload_ingest(dataset.source_dir / name, Path(name).name, settings.limits)
        begun = time.perf_counter()
        scan = await run_scan(ingest, workspace, NullSink(), settings=settings, analyzers=analyzers)
        durations["static"] = _elapsed_ms(begun)
        if router is None:
            return FileRecord(
                run=spec.name,
                file=name,
                started_at=started_at,
                complete=True,
                variants={"A": scan.static.findings},
                calls=[],
                stats={},
                durations_ms=durations,
                models=models,
                prompt_versions={},
            )

        chunks = sum(len(file.chunks) for file in scan.files)
        options = ReviewOptions(
            depth=Depth.STANDARD,
            allow_external=True,
            # Review first, style with what is left: one call per chunk means no style.
            max_review_calls=max(1, chunks if spec.kind is RunKind.MODEL else chunks * 2),
        )
        session = ReviewSession(router, options, NullSink())
        static = scan.static
        if spec.kind is RunKind.LLM_ONLY:
            # Secrets stay masked; only the findings and metrics are withheld.
            static = replace(static, findings=[], metrics=[])
        begun = time.perf_counter()
        reviewed = await session.review(scan.files, static, scan.ingest.root)
        durations["review"] = _elapsed_ms(begun)
        variants = {spec.variants[0]: reviewed}
        final = reviewed
        if spec.kind is RunKind.HYBRID:
            begun = time.perf_counter()
            final = await session.verify(reviewed)
            durations["verify"] = _elapsed_ms(begun)
            variants["E"] = final
        result = session.result(final, None)
        stats = asdict(result.stats)
        return FileRecord(
            run=spec.name,
            file=name,
            started_at=started_at,
            complete=stats["tasks_failed"] == 0,
            variants=variants,
            calls=result.calls,
            stats=stats,
            durations_ms=durations,
            models=models,
            prompt_versions=result.prompt_versions,
        )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
