"""Ruff: PEP 8 style, likely bugs, simplifications and performance anti-patterns in Python.

Ruff runs with ``--isolated``, so ``pyproject.toml`` or ``ruff.toml`` files in
an upload cannot change the rule set. The Python version and line length the
upload declares are respected; see :mod:`app.static.declared`.
Security rules (``S``) are left to Bandit, which reports CWE ids and confidence.
"""

import json
import re
from pathlib import Path

from app.errors import AnalyzerError
from app.findings import Category, Finding, Severity, shorten_title
from app.static.base import AnalysisTarget, AnalyzerResult, relative_to_root, run_tool
from app.static.declared import declared_settings
from app.static.process import python_tool

NAME = "ruff"
SELECTED_RULES = ("E", "W", "F", "B", "N", "UP", "SIM", "PERF", "C4", "RET")

# Checked longest prefix first, so specific codes win over their family.
_CLASSIFICATION: dict[str, tuple[Category, Severity]] = {
    "F821": (Category.BUG, Severity.HIGH),
    "F401": (Category.MAINTAINABILITY, Severity.LOW),
    "F841": (Category.MAINTAINABILITY, Severity.LOW),
    "E722": (Category.BUG, Severity.MEDIUM),
    "E9": (Category.BUG, Severity.HIGH),
    "F": (Category.BUG, Severity.MEDIUM),
    "B": (Category.BUG, Severity.MEDIUM),
    "PERF": (Category.PERFORMANCE, Severity.LOW),
    "C4": (Category.MAINTAINABILITY, Severity.LOW),
    "SIM": (Category.MAINTAINABILITY, Severity.LOW),
    "UP": (Category.MAINTAINABILITY, Severity.LOW),
    "RET": (Category.MAINTAINABILITY, Severity.LOW),
    "W": (Category.STYLE, Severity.INFO),
    "E": (Category.STYLE, Severity.LOW),
    "N": (Category.STYLE, Severity.LOW),
}
_SYNTAX_ERROR = (Category.BUG, Severity.MEDIUM)
_RULE_CODE = re.compile(r"[A-Z]+[0-9]+")


class RuffAnalyzer:
    """Runs ``ruff check`` over the Python files in the target."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Ruff only reviews Python."""
        return bool(target.files_with_suffix(".py"))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run Ruff in isolated mode and normalize its JSON output."""
        declared = declared_settings(target.root, target.files)
        result = await run_tool(
            target,
            python_tool(
                "ruff",
                "check",
                "--isolated",
                "--no-respect-gitignore",
                "--no-cache",
                "--exit-zero",
                "--output-format",
                "json",
                "--select",
                ",".join(SELECTED_RULES),
                "--line-length",
                str(declared.line_length),
                "--target-version",
                f"py3{declared.python_minor}",
                str(target.root),
            ),
        )
        return AnalyzerResult(findings=parse_output(result.stdout, target.root))


def rule_code(code: str | None) -> str | None:
    """The lint rule a diagnostic reports, or ``None`` for a syntax error.

    Ruff reports syntax errors without a code before 0.15 and as ``invalid-syntax``
    since; neither is a rule code such as ``E501``.
    """
    return code if code is not None and _RULE_CODE.fullmatch(code) else None


def classify(code: str | None) -> tuple[Category, Severity]:
    """Category and severity for a Ruff rule code; ``None`` means a syntax error."""
    if code is None:
        return _SYNTAX_ERROR
    for prefix in sorted(_CLASSIFICATION, key=len, reverse=True):
        if code.startswith(prefix):
            return _CLASSIFICATION[prefix]
    return Category.STYLE, Severity.LOW


def parse_output(stdout: str, root: Path) -> list[Finding]:
    """Normalize ``ruff check --output-format json`` output.

    Raises:
        AnalyzerError: If the output is not the expected JSON.
    """
    try:
        diagnostics = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise AnalyzerError("ruff produced invalid JSON") from error

    findings: list[Finding] = []
    for diagnostic in diagnostics:
        path = relative_to_root(diagnostic["filename"], root)
        if path is None:
            continue
        code = rule_code(diagnostic.get("code"))
        category, severity = classify(code)
        start = diagnostic["location"]
        end = diagnostic.get("end_location") or start
        message = diagnostic["message"]
        findings.append(
            Finding(
                file_path=path,
                start_line=start["row"],
                end_line=max(end["row"], start["row"]),
                start_column=start["column"],
                end_column=end["column"] if end["row"] == start["row"] else None,
                category=category,
                severity=severity,
                title=shorten_title(message),
                message=message,
                rule_id=code or "syntax-error",
                sources=[NAME],
            )
        )
    return findings
