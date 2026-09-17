"""Radon: cyclomatic complexity, maintainability index and size metrics for Python.

Radon reads options (such as exclusions) from configuration files in its
working directory; it runs from the empty scratch directory so an upload's
``setup.cfg`` or ``radon.cfg`` is never applied.
"""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.errors import AnalyzerError
from app.findings import Category, Finding, Severity
from app.static.base import (
    AnalysisTarget,
    AnalyzerResult,
    FileMetrics,
    relative_to_root,
    run_tool,
)
from app.static.process import python_tool

NAME = "radon"
LOW_MAINTAINABILITY_INDEX = 20.0
_COMPLEXITY_SEVERITY = {"D": Severity.LOW, "E": Severity.MEDIUM, "F": Severity.MEDIUM}


class RadonAnalyzer:
    """Measures Python complexity and size."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Radon only measures Python."""
        return bool(target.files_with_suffix(".py"))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run the complexity, maintainability and raw-metrics reports concurrently.

        A task group cancels the remaining reports as soon as one fails, and
        cancellation kills their processes instead of leaving them running.
        """
        root = str(target.root)
        try:
            async with asyncio.TaskGroup() as group:
                complexity, maintainability, raw = (
                    group.create_task(
                        run_tool(target, python_tool("radon", report, "--json", root))
                    )
                    for report in ("cc", "mi", "raw")
                )
        except ExceptionGroup as failures:
            raise failures.exceptions[0] from None
        cc_report = load_report(complexity.result().stdout)
        mi_report = load_report(maintainability.result().stdout)
        raw_report = load_report(raw.result().stdout)
        return AnalyzerResult(
            findings=[
                *complexity_findings(cc_report, target.root),
                *maintainability_findings(mi_report, target.root),
            ],
            metrics=file_metrics(raw_report, mi_report, target.root),
        )


def complexity_findings(report: dict[str, Any], root: Path) -> list[Finding]:
    """Findings for functions and methods ranked D or worse."""
    findings: list[Finding] = []
    for reported_path, blocks in report.items():
        path = relative_to_root(reported_path, root)
        if path is None or not isinstance(blocks, list):
            continue
        for block in _callables(blocks):
            severity = _COMPLEXITY_SEVERITY.get(block["rank"])
            if severity is None:
                continue
            name, complexity = block["name"], block["complexity"]
            findings.append(
                Finding(
                    file_path=path,
                    start_line=block["lineno"],
                    end_line=max(block["endline"], block["lineno"]),
                    category=Category.MAINTAINABILITY,
                    severity=severity,
                    title=f"'{name}' is too complex (cyclomatic complexity {complexity})"[:80],
                    message=(
                        f"'{name}' has cyclomatic complexity {complexity} (rank {block['rank']}), "
                        "which makes it hard to test and change. Consider splitting it into "
                        "smaller functions."
                    ),
                    rule_id="cyclomatic-complexity",
                    sources=[NAME],
                )
            )
    return findings


def maintainability_findings(report: dict[str, Any], root: Path) -> list[Finding]:
    """File-level findings for a maintainability index below 20."""
    findings: list[Finding] = []
    for reported_path, result in report.items():
        path = relative_to_root(reported_path, root)
        if path is None or "mi" not in result or result["mi"] >= LOW_MAINTAINABILITY_INDEX:
            continue
        findings.append(
            Finding(
                file_path=path,
                start_line=1,
                end_line=1,
                category=Category.MAINTAINABILITY,
                severity=Severity.MEDIUM,
                title=f"Low maintainability index ({result['mi']:.0f}/100)",
                message=(
                    f"The file's maintainability index is {result['mi']:.1f} out of 100. "
                    "Long, complex and sparsely commented code scores low."
                ),
                rule_id="maintainability-index",
                sources=[NAME],
            )
        )
    return findings


def file_metrics(
    raw_report: dict[str, Any], mi_report: dict[str, Any], root: Path
) -> list[FileMetrics]:
    """Line counts and maintainability index per file."""
    metrics: list[FileMetrics] = []
    for reported_path, raw in raw_report.items():
        path = relative_to_root(reported_path, root)
        if path is None or "loc" not in raw:
            continue
        maintainability = mi_report.get(reported_path, {})
        metrics.append(
            FileMetrics(
                path=path,
                lines=raw["loc"],
                source_lines=raw["sloc"],
                comment_lines=raw["comments"] + raw["multi"],
                blank_lines=raw["blank"],
                maintainability_index=maintainability.get("mi"),
            )
        )
    return metrics


def _callables(blocks: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Functions, methods and closures; classes only contribute their methods."""
    for block in blocks:
        if block["type"] != "class":
            yield block
        yield from _callables(block.get("methods", []))
        yield from _callables(block.get("closures", []))


def load_report(stdout: str) -> dict[str, Any]:
    """Parse one radon JSON report."""
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise AnalyzerError("radon produced invalid JSON") from error
    if not isinstance(report, dict):
        raise AnalyzerError("radon produced an unexpected report")
    return report
