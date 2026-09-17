from app.findings import REDACTED_EVIDENCE, Category, Finding, Severity
from app.static.dedupe import CREDENTIAL_ISSUE, deduplicate, issue_key


def finding(source: str, rule: str, line: int = 3, **overrides: object) -> Finding:
    values: dict[str, object] = {
        "file_path": "app/main.py",
        "start_line": line,
        "end_line": line,
        "category": Category.MAINTAINABILITY,
        "severity": Severity.LOW,
        "title": f"{source} {rule}",
        "message": f"{source} reports {rule}",
        "rule_id": rule,
        "sources": [source],
    }
    values.update(overrides)
    return Finding.model_validate(values)


def test_equivalent_rules_share_an_issue_key() -> None:
    assert issue_key(finding("ruff", "F401")) == issue_key(finding("vulture", "unused-import"))
    assert issue_key(finding("detect-secrets", "AWS Access Key")) == CREDENTIAL_ISSUE
    assert issue_key(finding("ruff", "E501")) == "ruff:E501"


def test_merges_equivalent_findings_from_different_tools_on_the_same_line() -> None:
    [merged] = deduplicate(
        [
            finding("ruff", "F401"),
            finding("vulture", "unused-import", confidence=0.9, end_line=4),
        ]
    )

    assert merged.sources == ["ruff", "vulture"]
    assert merged.confidence == 1.0
    assert merged.end_line == 4


def test_most_severe_finding_leads_and_redaction_is_preserved() -> None:
    bandit = finding(
        "bandit",
        "B105",
        category=Category.SECURITY,
        severity=Severity.LOW,
        evidence=REDACTED_EVIDENCE,
        cwe="CWE-259",
    )
    secrets = finding(
        "detect-secrets",
        "Secret Keyword",
        category=Category.SECURITY,
        severity=Severity.HIGH,
        evidence=REDACTED_EVIDENCE,
        cwe="CWE-798",
    )

    [merged] = deduplicate([bandit, secrets])

    assert merged.rule_id == "Secret Keyword"
    assert merged.severity is Severity.HIGH
    assert merged.sources == ["detect-secrets", "bandit"]
    assert merged.evidence == REDACTED_EVIDENCE
    assert merged.cwe == "CWE-798"


def test_keeps_same_tool_findings_on_one_line_separate() -> None:
    findings = deduplicate(
        [finding("ruff", "F401", start_column=8), finding("ruff", "F401", start_column=12)]
    )

    assert len(findings) == 2


def test_does_not_merge_different_lines_files_or_issues() -> None:
    findings = deduplicate(
        [
            finding("ruff", "F401", line=1),
            finding("vulture", "unused-import", line=2),
            finding("vulture", "unused-import", line=1, file_path="other.py"),
            finding("ruff", "E501", line=1),
        ]
    )

    assert len(findings) == 4
