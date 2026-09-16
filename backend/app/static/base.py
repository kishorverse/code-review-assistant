"""The contract every analyzer implements, and helpers for normalizing tool output."""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol

from pydantic import BaseModel, ConfigDict, NonNegativeInt

from app.errors import AnalyzerError
from app.findings import Finding
from app.static.process import ProcessResult, minimal_environment, run_process


class ToolStatus(StrEnum):
    """Outcome of one analyzer run."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class ToolRun(BaseModel):
    """What happened when an analyzer ran; shown in reports and the UI."""

    model_config = ConfigDict(frozen=True)

    tool: str
    status: ToolStatus
    duration_ms: NonNegativeInt
    finding_count: NonNegativeInt = 0
    message: str | None = None


class FunctionMetrics(BaseModel):
    """Size and complexity of one function or method."""

    model_config = ConfigDict(frozen=True)

    name: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    lines_of_code: int
    parameters: int


class FileMetrics(BaseModel):
    """Size and maintainability of one file. Fields a tool does not measure stay ``None``."""

    model_config = ConfigDict(frozen=True)

    path: str
    lines: int | None = None
    source_lines: int | None = None
    comment_lines: int | None = None
    blank_lines: int | None = None
    maintainability_index: float | None = None
    functions: list[FunctionMetrics] = []


@dataclass(frozen=True)
class AnalysisTarget:
    """The files an analyzer should examine.

    Attributes:
        root: Resolved directory containing only reviewable, extracted files.
        files: POSIX paths relative to ``root``.
        scratch: Empty directory for the tool's working directory, home and temp files.
            It never contains uploaded files, so tools find no project configuration there.
    """

    root: Path
    files: tuple[str, ...]
    scratch: Path

    def files_with_suffix(self, *suffixes: str) -> list[str]:
        """Files whose extension, ignoring case, is one of ``suffixes``."""
        wanted = {suffix.lower() for suffix in suffixes}
        return [name for name in self.files if PurePosixPath(name).suffix.lower() in wanted]


@dataclass(frozen=True)
class AnalyzerResult:
    """Findings and metrics produced by one analyzer."""

    findings: list[Finding] = field(default_factory=list)
    metrics: list[FileMetrics] = field(default_factory=list)


class Analyzer(Protocol):
    """A static analysis tool adapted to Margin's finding schema."""

    @property
    def name(self) -> str:
        """Stable tool name recorded in finding sources."""
        ...

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Whether the target contains files this analyzer understands."""
        ...

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run the tool and normalize its output.

        Raises:
            ToolUnavailableError: If the tool is not installed.
            AnalyzerError: If the tool ran but its output could not be used.
        """
        ...


async def run_tool(
    target: AnalysisTarget,
    argv: Sequence[str],
    *,
    accepted_exit_codes: Collection[int] = (0,),
    cwd: Path | None = None,
) -> ProcessResult:
    """Run an analyzer command with the minimal environment.

    Args:
        target: Supplies the scratch directory used as working directory by default.
        argv: The command.
        accepted_exit_codes: Exit codes that mean the tool ran (many linters exit
            non-zero when they find issues).
        cwd: Working directory override, for tools that must run from the root.

    Raises:
        ToolUnavailableError: If the executable is missing.
        AnalyzerError: If the tool exits with an unexpected code.
    """
    result = await run_process(
        argv, cwd=cwd or target.scratch, env=minimal_environment(target.scratch)
    )
    if result.returncode not in accepted_exit_codes:
        detail = next((line for line in reversed(result.stderr.splitlines()) if line.strip()), "")
        raise AnalyzerError(f"exited with code {result.returncode}: {detail[:200]}".rstrip(": "))
    return result


def relative_to_root(reported: str | Path, root: Path, base: Path | None = None) -> str | None:
    """Convert a path printed by a tool into a POSIX path relative to ``root``.

    Args:
        reported: Absolute path, or path relative to ``base``.
        root: The resolved scan root.
        base: Directory relative paths are resolved against; defaults to ``root``.

    Returns:
        The relative path, or ``None`` if it lies outside the root (for example
        a standard-library stub mypy reports on).
    """
    path = Path(reported)
    if not path.is_absolute():
        path = (base or root) / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def absolute_paths(target: AnalysisTarget, files: Iterable[str]) -> list[str]:
    """Absolute paths for relative file names, for tools run outside the root."""
    return [str(target.root.joinpath(*PurePosixPath(name).parts)) for name in files]
