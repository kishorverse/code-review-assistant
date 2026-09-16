"""Opengrep: pattern and data-flow security rules, using Margin's own rule files.

The rules live in ``app/static/rules`` and are written for this project, so no
third-party rule-pack license applies and adding a rule is a YAML change.

Security: Opengrep applies ``.semgrepignore`` files from its working directory,
and an uploaded one can hide every file even with ``--no-git-ignore``
(reproduced). Opengrep therefore runs from the scratch directory. The version
check is disabled, and Opengrep sends no telemetry.
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

from app.errors import AnalyzerError, ToolUnavailableError
from app.findings import Category, Finding, Severity, shorten_title
from app.static.base import AnalysisTarget, AnalyzerResult, relative_to_root, run_tool

NAME = "opengrep"
RULES_DIRECTORY = Path(__file__).resolve().parent.parent / "rules"
SOURCE_SUFFIXES = (".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
PER_FILE_TIMEOUT_SECONDS = 10

_SEVERITY = {"ERROR": Severity.HIGH, "WARNING": Severity.MEDIUM, "INFO": Severity.LOW}
_CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.5}


def find_executable(configured: str | None = None) -> str | None:
    """The Opengrep binary: an explicitly configured path, or ``opengrep`` on ``PATH``."""
    return configured or shutil.which("opengrep")


class OpengrepAnalyzer:
    """Runs Margin's security rules over Python, JavaScript and TypeScript."""

    name = NAME

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Opengrep rules exist for Python, JavaScript and TypeScript."""
        return bool(target.files_with_suffix(*SOURCE_SUFFIXES))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run the bundled rules and normalize the JSON results.

        Raises:
            ToolUnavailableError: If no Opengrep binary is installed.
        """
        if self._executable is None:
            raise ToolUnavailableError("opengrep is not installed")
        if sys.platform == "win32":
            # Opengrep aborts (0xC0000409) when the profile directory it is given has no
            # AppData\Local, and the minimal environment points the profile at scratch.
            local_app_data = target.scratch / "AppData" / "Local"
            await asyncio.to_thread(local_app_data.mkdir, parents=True, exist_ok=True)
        result = await run_tool(
            target,
            [
                self._executable,
                "scan",
                "--config",
                str(RULES_DIRECTORY),
                "--json",
                "--quiet",
                "--no-git-ignore",
                "--no-rewrite-rule-ids",
                "--disable-version-check",
                "--timeout",
                str(PER_FILE_TIMEOUT_SECONDS),
                "--jobs",
                "2",
                str(target.root),
            ],
            accepted_exit_codes=(0, 1),
        )
        return AnalyzerResult(findings=parse_output(result.stdout, target.root))


def parse_output(stdout: str, root: Path) -> list[Finding]:
    """Normalize Opengrep's JSON results.

    Raises:
        AnalyzerError: If the output is not the expected JSON.
    """
    try:
        results = json.loads(stdout)["results"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AnalyzerError("opengrep produced an unexpected report") from error

    findings: list[Finding] = []
    for result in results:
        path = relative_to_root(result["path"], root)
        if path is None:
            continue
        extra = result["extra"]
        metadata = extra.get("metadata", {})
        message = " ".join(extra["message"].split())
        start, end = result["start"], result["end"]
        cwe = metadata.get("cwe")
        findings.append(
            Finding(
                file_path=path,
                start_line=start["line"],
                end_line=max(end["line"], start["line"]),
                start_column=start["col"],
                end_column=end["col"] if end["line"] == start["line"] else None,
                category=_category(metadata.get("category")),
                severity=_SEVERITY.get(extra.get("severity", ""), Severity.LOW),
                title=shorten_title(message.split(". ")[0]),
                message=message,
                rule_id=result["check_id"],
                sources=[NAME],
                confidence=_CONFIDENCE.get(metadata.get("confidence", ""), 0.7),
                cwe=cwe if isinstance(cwe, str) and cwe.startswith("CWE-") else None,
            )
        )
    return findings


def _category(value: object) -> Category:
    try:
        return Category(str(value))
    except ValueError:
        return Category.SECURITY
