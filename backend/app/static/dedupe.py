"""Merge findings that different tools report for the same issue.

Tools overlap: Ruff and Vulture both find unused imports, Bandit and
detect-secrets both find hardcoded passwords. Showing both would double-count
the issue, so equivalent findings on the same line are merged into one that
records every source. Findings from the same tool are never merged with each
other, because two same-rule findings on one line are distinct issues (for
example two unused names in ``import os, sys``).
"""

from collections.abc import Iterable

from app.findings import REDACTED_EVIDENCE, Finding
from app.static.analyzers import detect_secrets

CREDENTIAL_ISSUE = "hardcoded-credential"

EQUIVALENT_RULES: dict[tuple[str, str], str] = {
    ("ruff", "F401"): "unused-import",
    ("vulture", "unused-import"): "unused-import",
    ("ruff", "F841"): "unused-variable",
    ("vulture", "unused-variable"): "unused-variable",
    ("bandit", "B105"): CREDENTIAL_ISSUE,
    ("bandit", "B106"): CREDENTIAL_ISSUE,
    ("bandit", "B107"): CREDENTIAL_ISSUE,
    ("opengrep", "python-shell-command-from-dynamic-input"): "shell-injection",
    ("bandit", "B602"): "shell-injection",
    ("bandit", "B605"): "shell-injection",
    ("opengrep", "python-sql-built-with-string-formatting"): "sql-injection",
    ("bandit", "B608"): "sql-injection",
    ("opengrep", "python-yaml-load-without-safe-loader"): "unsafe-yaml-load",
    ("bandit", "B506"): "unsafe-yaml-load",
    ("opengrep", "python-tls-certificate-verification-disabled"): "tls-verification-off",
    ("bandit", "B501"): "tls-verification-off",
    ("opengrep", "python-web-debug-mode-enabled"): "debug-mode",
    ("bandit", "B201"): "debug-mode",
    ("opengrep", "python-insecure-random-for-secret"): "insecure-random",
    ("bandit", "B311"): "insecure-random",
    ("opengrep", "python-password-hashed-with-fast-hash"): "weak-hash",
    ("bandit", "B324"): "weak-hash",
    ("opengrep", "python-insecure-temporary-file"): "insecure-temp-file",
    ("bandit", "B306"): "insecure-temp-file",
    ("opengrep", "python-eval-of-dynamic-value"): "dynamic-eval",
    ("bandit", "B307"): "dynamic-eval",
    ("radon", "cyclomatic-complexity"): "complexity",
    ("lizard", "function-complexity"): "complexity",
}
_ALWAYS_EQUIVALENT_SOURCES = {detect_secrets.NAME: CREDENTIAL_ISSUE}


def issue_key(finding: Finding) -> str:
    """The kind of issue a finding describes, shared by equivalent rules across tools."""
    source = finding.sources[0]
    if source in _ALWAYS_EQUIVALENT_SOURCES:
        return _ALWAYS_EQUIVALENT_SOURCES[source]
    rule = finding.rule_id or ""
    return EQUIVALENT_RULES.get((source, rule), f"{source}:{rule}")


def deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    """Merge equivalent findings from different tools on the same line, keeping input order."""
    groups: dict[tuple[str, int, str], list[list[Finding]]] = {}
    for finding in findings:
        buckets = groups.setdefault((finding.file_path, finding.start_line, issue_key(finding)), [])
        bucket = next(
            (b for b in buckets if not any(set(f.sources) & set(finding.sources) for f in b)),
            None,
        )
        if bucket is None:
            buckets.append([finding])
        else:
            bucket.append(finding)
    return [merge(bucket) for buckets in groups.values() for bucket in buckets]


def merge(findings: list[Finding]) -> Finding:
    """Combine equivalent findings: the most severe one leads, and every source is kept."""
    if len(findings) == 1:
        return findings[0]
    lead = max(findings, key=lambda f: (f.severity.rank, f.confidence))
    sources = list(dict.fromkeys(source for f in [lead, *findings] for source in f.sources))
    redacted = any(f.evidence == REDACTED_EVIDENCE for f in findings)
    return lead.model_copy(
        update={
            "sources": sources,
            "end_line": max(f.end_line for f in findings),
            "confidence": max(f.confidence for f in findings),
            "cwe": lead.cwe or next((f.cwe for f in findings if f.cwe), None),
            "evidence": REDACTED_EVIDENCE if redacted else lead.evidence,
        }
    )
