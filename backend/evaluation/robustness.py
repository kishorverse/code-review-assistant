"""Static scans of third-party repositories: how Margin holds up on real code.

The seeded dataset measures accuracy on code written for this evaluation. Real
repositories measure what it cannot: whether the pipeline survives sizes,
languages, generated files and broken corners it has never seen, and what a
first scan of mature, widely reviewed code actually reports.

Each repository is pinned to a commit, so a rerun scans the same code. Cloning
needs the network; the results are committed, so the tables can be read and the
report rebuilt without it.
"""

import asyncio
import shutil
import tempfile
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.errors import MarginError
from app.events import NullSink
from app.findings import Severity
from app.ingest.storage import ScanStorage, new_scan_id
from app.pipeline import ScanSettings, directory_ingest, run_scan
from app.report.document import build_report
from app.review.planner import DEFAULT_MIN_CONFIDENCE
from app.static.base import ToolStatus
from app.static.runner import default_analyzers
from evaluation.dataset import EVAL_DIR

CACHE_DIR = EVAL_DIR / "datasets" / "external"
"""Where checkouts are kept. Ignored by git: the pinned commits are the record."""

GIT_TIMEOUT_SECONDS = 600.0
SEVERITIES = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)
NO_VALUE = "—"


class CloneError(Exception):
    """A repository could not be fetched at its pinned commit."""


@dataclass(frozen=True)
class Repository:
    """A third-party repository to scan, pinned to one commit.

    Attributes:
        name: ``owner/repo`` on GitHub, used as the row label and cache directory.
        language: The language it is written in, as its authors describe it.
        license: Its license, recorded because its code is fetched and analyzed.
    """

    name: str
    url: str
    commit: str
    language: str
    license: str


REPOSITORIES: tuple[Repository, ...] = (
    Repository(
        name="psf/requests",
        url="https://github.com/psf/requests.git",
        commit="dae7ef63b4df6eded86637f251fc4e3a06c3b479",  # pragma: allowlist secret
        language="Python",
        license="Apache-2.0",
    ),
    Repository(
        name="pallets/click",
        url="https://github.com/pallets/click.git",
        commit="6aabf099bfdd4c1e75fe8d0e0d4241372b988ab1",  # pragma: allowlist secret
        language="Python",
        license="BSD-3-Clause",
    ),
    Repository(
        name="expressjs/express",
        url="https://github.com/expressjs/express.git",
        commit="9a34acf03cb818ff3f8bc40e44176e277a25cbb9",  # pragma: allowlist secret
        language="JavaScript",
        license="MIT",
    ),
    Repository(
        name="sindresorhus/got",
        url="https://github.com/sindresorhus/got.git",
        commit="e1d87d2ced01d5b7d855a7dc8b091bf7b014a1e4",  # pragma: allowlist secret
        language="TypeScript",
        license="MIT",
    ),
    Repository(
        name="gorilla/mux",
        url="https://github.com/gorilla/mux.git",
        commit="db9d1d0073d27a0a2d9a8c1bc52aa0af4374d265",  # pragma: allowlist secret
        language="Go",
        license="BSD-3-Clause",
    ),
    Repository(
        name="google/gson",
        url="https://github.com/google/gson.git",
        commit="854c8255b625cf1e13c701a83ea9ccb4caaa576a",  # pragma: allowlist secret
        language="Java",
        license="Apache-2.0",
    ),
)
"""Widely used, permissively licensed projects, one per supported language.

The pinned commits read as high-entropy strings to detect-secrets, which is the
same false positive this benchmark measures on real repositories (evaluation §6).
"""


@dataclass(frozen=True)
class Scan:
    """What one repository's static scan produced.

    Attributes:
        ingested: Files taken from the checkout, after the ingest filters.
        reviewed: Of those, the files a language adapter understood.
        languages: Language to number of reviewed files.
        tools: Analyzer name to the status of its run.
        rules: The rules behind the most findings.
        error: Set when the scan was rejected outright; every count is then zero.
    """

    repository: str
    language: str
    commit: str
    ingested: int = 0
    reviewed: int = 0
    skipped: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    kloc: float = 0.0
    seconds: float = 0.0
    severities: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    rules: dict[str, int] = field(default_factory=dict)
    score: int = 0
    grade: str = ""
    error: str | None = None

    @property
    def tools_ran(self) -> int:
        """Analyzers that ran; the rest had no file of a language they read."""
        return sum(status == ToolStatus.OK for status in self.tools.values())

    @property
    def findings(self) -> int:
        """Findings in the default report."""
        return sum(self.severities.values())


async def _git(*args: str, cwd: Path) -> str:
    """Run one git command in ``cwd`` and return its output.

    Raises:
        CloneError: If git is missing, fails or does not finish in time.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as error:
        raise CloneError(f"git {args[0]} could not start: {error}") from error
    try:
        async with asyncio.timeout(GIT_TIMEOUT_SECONDS):
            stdout, _ = await process.communicate()
    except TimeoutError as error:
        process.kill()
        raise CloneError(f"git {args[0]} timed out after {GIT_TIMEOUT_SECONDS:.0f}s") from error
    output = stdout.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise CloneError(f"git {args[0]} failed: {output or process.returncode}")
    return output


async def prepare(repository: Repository, cache_dir: Path = CACHE_DIR) -> Path:
    """Check the pinned commit out into the cache, reusing one already there.

    Fetching a single commit at depth 1 keeps each checkout to the code itself
    rather than its history.

    Raises:
        CloneError: If the commit could not be fetched.
    """
    path = cache_dir / repository.name.replace("/", "__")
    if (path / ".git").exists():
        try:
            if await _git("rev-parse", "HEAD", cwd=path) == repository.commit:
                return path
        except CloneError:
            # An interrupted fetch leaves a repository without a HEAD: start over.
            shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    await _git("init", "--quiet", cwd=path)
    await _git("fetch", "--depth", "1", "--quiet", repository.url, repository.commit, cwd=path)
    await _git("checkout", "--quiet", "--force", "FETCH_HEAD", cwd=path)
    await _git("clean", "--quiet", "--force", "-d", cwd=path)
    return path


async def scan(repository: Repository, path: Path) -> Scan:
    """Scan a checkout exactly as ``margin scan <directory>`` does, without models.

    A repository the ingest limits reject is recorded with its error rather than
    raising: a benchmark reports what happened to every entry.
    """
    settings = ScanSettings()
    analyzers = default_analyzers(get_settings().opengrep_path)
    ingest = directory_ingest(path, settings.limits)
    try:
        with tempfile.TemporaryDirectory(
            prefix="margin-robustness-", ignore_cleanup_errors=True
        ) as temp:
            workspace = ScanStorage(Path(temp)).create(new_scan_id())
            started = time.perf_counter()
            result = await run_scan(
                ingest, workspace, NullSink(), settings=settings, analyzers=analyzers
            )
            seconds = time.perf_counter() - started
    except MarginError as error:
        return Scan(
            repository=repository.name,
            language=repository.language,
            commit=repository.commit[:7],
            error=f"{type(error).__name__}: {error}",
        )
    report = build_report(
        result,
        source=repository.name,
        min_confidence=DEFAULT_MIN_CONFIDENCE,
        generated_at=datetime.now(UTC),
    )
    return Scan(
        repository=repository.name,
        language=repository.language,
        commit=repository.commit[:7],
        ingested=len(report.scanned_files),
        reviewed=len(report.files),
        skipped=len(report.skipped_files),
        languages=dict(Counter(file.language for file in report.files).most_common()),
        kloc=report.score.kloc,
        seconds=round(seconds, 1),
        severities={
            severity.value: report.summary.by_severity.get(severity.value, 0)
            for severity in SEVERITIES
        },
        categories=report.summary.by_category,
        tools={run.tool: run.status.value for run in report.tool_runs},
        rules=dict(
            Counter(
                finding.rule_id for finding in report.reported_findings() if finding.rule_id
            ).most_common(3)
        ),
        score=report.score.score,
        grade=report.score.grade,
    )


async def benchmark(
    repositories: Sequence[Repository] = REPOSITORIES, cache_dir: Path = CACHE_DIR
) -> list[Scan]:
    """Fetch and scan every repository, one after another.

    A repository that cannot be fetched is recorded and the run carries on, so
    one unreachable host does not cost the whole benchmark.
    """
    scans = []
    for repository in repositories:
        try:
            path = await prepare(repository, cache_dir)
        except CloneError as error:
            scans.append(
                Scan(
                    repository=repository.name,
                    language=repository.language,
                    commit=repository.commit[:7],
                    error=str(error),
                )
            )
            continue
        scans.append(await scan(repository, path))
    return scans


def to_markdown(scans: Sequence[Scan]) -> str:
    """The robustness tables quoted in ``docs/evaluation.md``."""
    done = [item for item in scans if item.error is None]
    rows = [
        f"Scanned {datetime.now(UTC):%Y-%m-%d} UTC: static analysis only, at the default depth, "
        "with no API keys. Each repository is pinned to the commit shown.",
        "",
        "| Repository | Language | Commit | Files | Reviewed | Languages seen | Analyzers "
        "| Seconds | Files per minute |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in done:
        languages = ", ".join(f"{name} {count}" for name, count in item.languages.items())
        per_minute = item.reviewed * 60 / item.seconds if item.seconds else 0.0
        rows.append(
            f"| {item.repository} | {item.language} | `{item.commit}` | {item.ingested} "
            f"| {item.reviewed} | {languages or NO_VALUE} | {item.tools_ran} of {len(item.tools)} "
            f"| {item.seconds:.1f} | {per_minute:.0f} |"
        )
    rows += [
        "",
        "| Repository | KLOC | Critical | High | Medium | Low | Findings per KLOC | Score "
        "| Most reported rules |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in done:
        counts = " | ".join(str(item.severities.get(severity.value, 0)) for severity in SEVERITIES)
        density = item.findings / item.kloc if item.kloc else 0.0
        rules = ", ".join(f"{rule} ({count})" for rule, count in item.rules.items())
        rows.append(
            f"| {item.repository} | {item.kloc:.1f} | {counts} | {density:.0f} "
            f"| {item.score}/100 ({item.grade}) | {rules or NO_VALUE} |"
        )
    problems = [f"- **{item.repository}**: {item.error}" for item in scans if item.error]
    problems += [
        f"- **{item.repository}**: {tool} {status}"
        for item in done
        for tool, status in item.tools.items()
        if status not in (ToolStatus.OK, ToolStatus.SKIPPED)
    ]
    if problems:
        rows += ["", "Failures:", *problems]
    return "\n".join(rows) + "\n"
