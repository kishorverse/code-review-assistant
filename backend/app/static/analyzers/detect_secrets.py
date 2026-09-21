"""detect-secrets: hardcoded credentials in any text file.

detect-secrets only reports files given relative to its working directory, so
this is the one tool that runs from the scan root. That is safe because it
loads no project configuration or plugins by default, and ``python -I`` stops
uploaded modules from shadowing its imports. Findings never include the
secret: evidence is redacted and messages name only the kind of secret.
"""

import json
from pathlib import Path

from app.errors import AnalyzerError
from app.findings import REDACTED_EVIDENCE, Category, Finding, Severity
from app.static.base import (
    AnalysisTarget,
    AnalyzerResult,
    is_test_path,
    relative_to_root,
    run_tool,
)
from app.static.process import python_tool

NAME = "detect-secrets"
CWE_HARDCODED_CREDENTIALS = "CWE-798"

# "pragma: allowlist secret" comments serve a repository's own CI. In an upload they
# would let the uploader hide secrets from the scan and from redaction.
ALLOWLIST_FILTER = "detect_secrets.filters.allowlist.is_line_allowlisted"

# Keyword and entropy detectors also match non-secrets such as test fixtures.
_HEURISTIC_TYPES = frozenset(
    {"Secret Keyword", "Base64 High Entropy String", "Hex High Entropy String"}
)

# Test files are full of credentials written to be fake, and detect-secrets cannot
# tell them from live ones: on express and got, 78 of 81 high-severity secret
# findings were in tests (evaluation section 6). They are still reported, one step
# down, so a real secret committed in a test is not hidden.
_TEST_NOTE = (
    " This file looks like test code, so the value may be a fixture rather than a "
    "live credential; it is reported a step below the severity a secret in "
    "production code would get."
)


class DetectSecretsAnalyzer:
    """Scans every extracted file for committed credentials."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """Secrets can hide in any text file."""
        return bool(target.files)

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run ``detect-secrets scan --all-files`` from the scan root."""
        result = await run_tool(
            target,
            python_tool(
                "detect_secrets", "scan", "--all-files", "--disable-filter", ALLOWLIST_FILTER, "."
            ),
            cwd=target.root,
        )
        findings, hashes = parse_output(result.stdout, target.root)
        return AnalyzerResult(findings=findings, secret_hashes=hashes)


def parse_output(stdout: str, root: Path) -> tuple[list[Finding], frozenset[str]]:
    """Normalize a detect-secrets baseline report.

    Returns:
        The findings, and the SHA-1 digests of the detected values, which let other
        stages mask copies of a secret that detect-secrets reported only once.

    Raises:
        AnalyzerError: If the report is not the expected JSON.
    """
    try:
        results = json.loads(stdout)["results"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AnalyzerError("detect-secrets produced an unexpected report") from error

    findings: list[Finding] = []
    hashes: set[str] = set()
    for reported_path, secrets in results.items():
        path = relative_to_root(reported_path, root)
        if path is None:
            continue
        in_tests = is_test_path(path)
        for secret in secrets:
            hashes.add(secret["hashed_secret"])
            kind = secret["type"]
            findings.append(
                Finding(
                    file_path=path,
                    start_line=secret["line_number"],
                    end_line=secret["line_number"],
                    category=Category.SECURITY,
                    severity=Severity.MEDIUM if in_tests else Severity.HIGH,
                    title=f"Possible hardcoded secret ({kind})"[:80],
                    message=(
                        f"A value that looks like a {kind.lower()} is committed to the code. "
                        "Move it to configuration or a secrets manager, and rotate it if real."
                        + (_TEST_NOTE if in_tests else "")
                    ),
                    evidence=REDACTED_EVIDENCE,
                    rule_id=kind,
                    sources=[NAME],
                    confidence=0.6 if kind in _HEURISTIC_TYPES else 0.9,
                    cwe=CWE_HARDCODED_CREDENTIALS,
                )
            )
    return findings, frozenset(hashes)
