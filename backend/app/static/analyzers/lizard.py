"""Lizard: function-level complexity, length and parameter counts for every language.

Lizard provides the per-function metrics for all languages and flags overly
long functions and long parameter lists. Its complexity findings are limited
to non-Python code because Radon already ranks Python complexity.
"""

import csv
import io
from collections import defaultdict
from pathlib import PurePosixPath

from app.findings import Category, Finding, Severity
from app.static.base import (
    AnalysisTarget,
    AnalyzerResult,
    FileMetrics,
    FunctionMetrics,
    relative_to_root,
    run_tool,
)
from app.static.process import python_tool

NAME = "lizard"
MAX_COMPLEXITY = 15
MAX_LENGTH = 80
MAX_PARAMETERS = 6

# Extensions Lizard analyzes that Margin also reviews.
SOURCE_SUFFIXES = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".go")
_COLUMNS = (
    "nloc",
    "ccn",
    "tokens",
    "parameters",
    "length",
    "location",
    "file",
    "name",
    "long_name",
    "start",
    "end",
)


class LizardAnalyzer:
    """Measures every function and flags the unwieldy ones."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Lizard reviews any supported source language."""
        return bool(target.files_with_suffix(*SOURCE_SUFFIXES))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run Lizard with CSV output over the whole target."""
        result = await run_tool(
            target, python_tool("lizard", "--csv", "--no-gitignore", str(target.root))
        )
        findings, metrics = parse_output(result.stdout, target)
        return AnalyzerResult(findings=findings, metrics=metrics)


def parse_output(stdout: str, target: AnalysisTarget) -> tuple[list[Finding], list[FileMetrics]]:
    """Turn Lizard's CSV rows into findings and per-file function metrics."""
    reviewed = set(target.files_with_suffix(*SOURCE_SUFFIXES))
    functions: dict[str, list[FunctionMetrics]] = defaultdict(list)
    findings: list[Finding] = []

    for row in csv.reader(io.StringIO(stdout)):
        if len(row) != len(_COLUMNS):
            continue
        record = dict(zip(_COLUMNS, row, strict=True))
        path = relative_to_root(record["file"], target.root)
        if path is None or path not in reviewed:
            continue
        function = FunctionMetrics(
            name=record["name"],
            start_line=int(record["start"]),
            end_line=int(record["end"]),
            cyclomatic_complexity=int(record["ccn"]),
            lines_of_code=int(record["nloc"]),
            parameters=int(record["parameters"]),
        )
        functions[path].append(function)
        findings.extend(_findings_for(path, function, int(record["length"])))

    metrics = [FileMetrics(path=path, functions=items) for path, items in sorted(functions.items())]
    return findings, metrics


def _findings_for(path: str, function: FunctionMetrics, length: int) -> list[Finding]:
    checks: list[tuple[bool, str, str, str]] = [
        (
            function.cyclomatic_complexity > MAX_COMPLEXITY
            and PurePosixPath(path).suffix.lower() != ".py",
            "function-complexity",
            f"'{function.name}' is too complex (cyclomatic complexity "
            f"{function.cyclomatic_complexity})",
            "Many independent paths make the function hard to test and change.",
        ),
        (
            length > MAX_LENGTH,
            "long-function",
            f"'{function.name}' is long ({length} lines)",
            f"Functions over {MAX_LENGTH} lines are hard to read; split out cohesive steps.",
        ),
        (
            function.parameters > MAX_PARAMETERS,
            "too-many-parameters",
            f"'{function.name}' takes {function.parameters} parameters",
            "Long parameter lists are easy to misuse; group related values into an object.",
        ),
    ]
    return [
        Finding(
            file_path=path,
            start_line=function.start_line,
            end_line=max(function.end_line, function.start_line),
            category=Category.MAINTAINABILITY,
            severity=Severity.LOW,
            title=title[:80],
            message=f"{title}. {advice}",
            rule_id=rule_id,
            sources=[NAME],
        )
        for triggered, rule_id, title, advice in checks
        if triggered
    ]
