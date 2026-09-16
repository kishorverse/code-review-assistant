"""Vulture: dead code in Python.

Only results at 80% confidence or higher are kept; below that, Vulture flags
functions that are merely called from outside the project. Vulture reads
``[tool.vulture]`` from ``pyproject.toml`` in its working directory, so it runs
from the scratch directory where an upload's settings cannot hide results.
"""

import re
from pathlib import Path

from app.findings import Category, Finding, Severity
from app.static.base import AnalysisTarget, AnalyzerResult, relative_to_root, run_tool
from app.static.process import python_tool

NAME = "vulture"
MIN_CONFIDENCE = 80

# Exit codes: 0 nothing found, 1 invalid input in some file, 3 dead code found.
_ACCEPTED_EXIT_CODES = (0, 1, 3)
_LINE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): (?P<message>(?P<kind>unused \w+|unreachable code).*?) "
    r"\((?P<confidence>\d+)% confidence(?:, (?P<size>\d+) lines?)?\)$"
)


class VultureAnalyzer:
    """Finds unused and unreachable Python code."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Vulture only reviews Python."""
        return bool(target.files_with_suffix(".py"))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run Vulture and parse its line-oriented report."""
        result = await run_tool(
            target,
            python_tool("vulture", str(target.root), "--min-confidence", str(MIN_CONFIDENCE)),
            accepted_exit_codes=_ACCEPTED_EXIT_CODES,
        )
        return AnalyzerResult(findings=parse_output(result.stdout, target.root))


def parse_output(stdout: str, root: Path) -> list[Finding]:
    """Normalize Vulture's ``path:line: message (N% confidence)`` lines."""
    findings: list[Finding] = []
    for line in stdout.splitlines():
        match = _LINE.match(line.strip())
        if match is None:
            continue
        path = relative_to_root(match["path"], root)
        if path is None:
            continue
        start = int(match["line"])
        size = int(match["size"] or 1)
        message = match["message"][0].upper() + match["message"][1:]
        findings.append(
            Finding(
                file_path=path,
                start_line=start,
                end_line=start + size - 1,
                category=Category.MAINTAINABILITY,
                severity=Severity.LOW,
                title=message[:80],
                message=f"{message}. Remove it or, if it is used dynamically, document why.",
                rule_id=match["kind"].replace(" ", "-"),
                sources=[NAME],
                confidence=int(match["confidence"]) / 100,
            )
        )
    return findings
