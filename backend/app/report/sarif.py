"""SARIF 2.1.0 export, for GitHub code scanning, IDEs and other CI tools.

Mapping choices:

- One run, with one rule per rule id in first-seen order. Findings without a
  rule id use their first source's name.
- Levels: critical and high become ``error``, medium ``warning``, low and info ``note``.
- Security rules carry a ``security-severity`` score, which GitHub uses to rank alerts.
- Findings dismissed by AI review or rejected by a reviewer are exported with an
  external, accepted suppression and its justification, so they show up as
  dismissed instead of disappearing.
- AI-only findings below the report's confidence threshold are left out.
- Every result has a fingerprint from its rule, file and evidence, so the same
  issue keeps its identity when line numbers shift between scans.
"""

import hashlib
from typing import Any

from app.findings import Finding, FindingStatus, Severity
from app.report.document import Report
from app.review.merge import is_unconfident

SCHEMA_URI = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
INFORMATION_URI = "https://github.com/kishorverse/code-review-assistant"
SOURCE_ROOT = "%SRCROOT%"
FINGERPRINT_KEY = "marginFindingHash/v1"

LEVELS = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}
SECURITY_SEVERITY = {
    Severity.CRITICAL: 9.5,
    Severity.HIGH: 7.5,
    Severity.MEDIUM: 5.0,
    Severity.LOW: 2.0,
    Severity.INFO: 0.0,
}
SUPPRESSED = {
    FindingStatus.DISMISSED_BY_AI: "Dismissed by AI review",
    FindingStatus.REJECTED: "Rejected by a reviewer",
}


def to_sarif(report: Report) -> dict[str, Any]:
    """The report as a SARIF 2.1.0 log."""
    exported = [f for f in report.findings if not is_unconfident(f, report.min_confidence)]
    rule_ids = list(dict.fromkeys(rule_id(finding) for finding in exported))
    rule_index = {rule: index for index, rule in enumerate(rule_ids)}
    return {
        "$schema": SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Margin",
                        "version": report.tool.version,
                        "informationUri": INFORMATION_URI,
                        "rules": [_rule(rule, exported) for rule in rule_ids],
                    }
                },
                "results": [_result(finding, rule_index[rule_id(finding)]) for finding in exported],
                "properties": {
                    "qualityScore": report.score.score,
                    "grade": report.score.grade,
                    "scoreFormula": report.score.formula,
                },
            }
        ],
    }


def rule_id(finding: Finding) -> str:
    """The SARIF rule a finding belongs to."""
    return finding.rule_id or finding.sources[0]


def fingerprint(finding: Finding) -> str:
    """A hash that identifies the same issue across scans, independent of line numbers."""
    evidence = " ".join((finding.evidence or finding.title).split())
    material = "\x1f".join([rule_id(finding), finding.file_path, evidence])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _rule(rule: str, findings: list[Finding]) -> dict[str, Any]:
    members = [finding for finding in findings if rule_id(finding) == rule]
    first = members[0]
    tags = sorted({finding.category.value for finding in members} | _cwes(members))
    properties: dict[str, Any] = {"tags": tags}
    if any(finding.category.value == "security" for finding in members):
        worst = max(SECURITY_SEVERITY[finding.severity] for finding in members)
        properties["security-severity"] = f"{worst:.1f}"
    return {
        "id": rule,
        "shortDescription": {"text": first.title},
        "defaultConfiguration": {"level": LEVELS[first.severity]},
        "properties": properties,
    }


def _result(finding: Finding, rule_index: int) -> dict[str, Any]:
    region: dict[str, Any] = {"startLine": finding.start_line, "endLine": finding.end_line}
    if finding.start_column is not None:
        region["startColumn"] = finding.start_column
    if finding.end_column is not None:
        region["endColumn"] = finding.end_column
    if finding.evidence:
        region["snippet"] = {"text": finding.evidence}
    result: dict[str, Any] = {
        "ruleId": rule_id(finding),
        "ruleIndex": rule_index,
        "level": LEVELS[finding.severity],
        "message": {"text": finding.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file_path, "uriBaseId": SOURCE_ROOT},
                    "region": region,
                }
            }
        ],
        "partialFingerprints": {FINGERPRINT_KEY: fingerprint(finding)},
        "properties": _properties(finding),
    }
    if finding.status in SUPPRESSED:
        justification = SUPPRESSED[finding.status]
        if finding.status is FindingStatus.DISMISSED_BY_AI and finding.ai_note:
            justification = finding.ai_note
        result["suppressions"] = [
            {"kind": "external", "status": "accepted", "justification": justification}
        ]
    return result


def _properties(finding: Finding) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "severity": finding.severity.value,
        "category": finding.category.value,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "sources": finding.sources,
    }
    optional = {
        "verifiedBy": finding.verified_by or None,
        "cwe": finding.cwe,
        "rationale": finding.rationale,
        "suggestion": finding.suggestion,
        "aiNote": finding.ai_note,
    }
    properties.update({key: value for key, value in optional.items() if value is not None})
    return properties


def _cwes(findings: list[Finding]) -> set[str]:
    return {f"external/cwe/{finding.cwe.lower()}" for finding in findings if finding.cwe}
