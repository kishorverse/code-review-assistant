"""Bandit: security issues in Python, with CWE ids and confidence.

Three measures keep an upload from weakening the scan:

* ``--ini`` points at Margin's own empty file, because Bandit otherwise reads a
  ``.bandit`` file from the scanned project, which can skip checks.
* ``--ignore-nosec`` reports issues even where the code says ``# nosec``.
* Messages for hardcoded passwords are replaced, because Bandit quotes the
  password in them, and their evidence is redacted.
"""

import json
from pathlib import Path

from app.errors import AnalyzerError
from app.findings import REDACTED_EVIDENCE, Category, Finding, Severity, shorten_title
from app.static.base import AnalysisTarget, AnalyzerResult, relative_to_root, run_tool
from app.static.process import python_tool

NAME = "bandit"
INI_FILE = Path(__file__).with_name("bandit.ini")

# Import-only warnings duplicate the call-site findings for the same module,
# and assert_used flags every test file.
SKIPPED_TESTS = ("B101", "B403", "B404")
HARDCODED_PASSWORD_TESTS = frozenset({"B105", "B106", "B107"})

_SEVERITY = {
    ("HIGH", "HIGH"): Severity.HIGH,
    ("HIGH", "MEDIUM"): Severity.MEDIUM,
    ("MEDIUM", "HIGH"): Severity.MEDIUM,
    ("MEDIUM", "MEDIUM"): Severity.MEDIUM,
}
_CONFIDENCE = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.4}


class BanditAnalyzer:
    """Runs Bandit recursively over the target."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Bandit only reviews Python."""
        return bool(target.files_with_suffix(".py"))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run Bandit and normalize its JSON report."""
        result = await run_tool(
            target,
            python_tool(
                "bandit",
                "--format",
                "json",
                "--quiet",
                "--ignore-nosec",
                "--ini",
                str(INI_FILE),
                "--skip",
                ",".join(SKIPPED_TESTS),
                "--recursive",
                str(target.root),
            ),
            accepted_exit_codes=(0, 1),
        )
        return AnalyzerResult(findings=parse_output(result.stdout, target.root))


def severity_for(issue_severity: str, issue_confidence: str) -> Severity:
    """Combine Bandit's severity and confidence; critical is reserved for LLM confirmation."""
    return _SEVERITY.get((issue_severity, issue_confidence), Severity.LOW)


def parse_output(stdout: str, root: Path) -> list[Finding]:
    """Normalize a Bandit JSON report.

    Raises:
        AnalyzerError: If the report is not the expected JSON.
    """
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise AnalyzerError("bandit produced invalid JSON") from error

    findings: list[Finding] = []
    for issue in report.get("results", []):
        path = relative_to_root(issue["filename"], root)
        if path is None:
            continue
        test_id = issue["test_id"]
        is_password = test_id in HARDCODED_PASSWORD_TESTS
        message = "Possible hardcoded password." if is_password else issue["issue_text"]
        line_range = issue.get("line_range") or [issue["line_number"]]
        cwe_id = (issue.get("issue_cwe") or {}).get("id")
        findings.append(
            Finding(
                file_path=path,
                start_line=issue["line_number"],
                end_line=max(max(line_range), issue["line_number"]),
                start_column=issue["col_offset"] + 1,
                category=Category.SECURITY,
                severity=severity_for(issue["issue_severity"], issue["issue_confidence"]),
                title=shorten_title(message),
                message=message,
                evidence=REDACTED_EVIDENCE if is_password else None,
                rule_id=test_id,
                sources=[NAME],
                confidence=_CONFIDENCE.get(issue["issue_confidence"], 0.4),
                cwe=f"CWE-{cwe_id}" if cwe_id else None,
            )
        )
    return findings
