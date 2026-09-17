import json
from pathlib import Path

import pytest

from app.errors import AnalyzerError
from app.findings import REDACTED_EVIDENCE, Category, Severity
from app.static.analyzers.bandit import BanditAnalyzer, parse_output, severity_for
from tests.static.conftest import TargetFactory, by_rule

HIDDEN_VALUE = "correct-horse-battery"

SAMPLE = f"""
    import pickle
    import subprocess

    import yaml

    DB_PASSWORD = "{HIDDEN_VALUE}"


    def run(name):
        return subprocess.call("ls " + name, shell=True)  # nosec


    def load(blob, text):
        return pickle.loads(blob), yaml.load(text)


    def check(value):
        assert value
"""


async def test_reports_security_issues_with_cwe_and_ignores_nosec(
    make_target: TargetFactory,
) -> None:
    target = make_target({"app/tasks.py": SAMPLE})

    result = await BanditAnalyzer().analyze(target)

    findings = by_rule(result.findings)
    assert {"B602", "B301", "B506", "B105"} <= findings.keys()
    shell = findings["B602"]
    assert (shell.file_path, shell.start_line) == ("app/tasks.py", 10)
    assert shell.severity is Severity.HIGH
    assert shell.cwe == "CWE-78"
    assert shell.category is Category.SECURITY
    assert "B101" not in findings
    assert "B403" not in findings


async def test_hardcoded_password_is_never_echoed(make_target: TargetFactory) -> None:
    target = make_target({"app/tasks.py": SAMPLE})

    result = await BanditAnalyzer().analyze(target)

    password = by_rule(result.findings)["B105"]
    assert password.evidence == REDACTED_EVIDENCE
    assert HIDDEN_VALUE not in password.message
    assert HIDDEN_VALUE not in password.title


async def test_bandit_file_inside_the_upload_cannot_limit_or_break_checks(
    make_target: TargetFactory,
) -> None:
    # Without --ini, Bandit reads this file from the scanned project: `tests` limits the run
    # to assert checks and conflicts with the command-line skips, so no report is produced.
    target = make_target(
        {"app/tasks.py": SAMPLE, ".bandit": "[bandit]\ntests = B101\nskips = B602,B301,B506\n"}
    )

    result = await BanditAnalyzer().analyze(target)

    assert {"B602", "B301", "B506"} <= by_rule(result.findings).keys()


@pytest.mark.parametrize(
    ("severity", "confidence", "expected"),
    [
        ("HIGH", "HIGH", Severity.HIGH),
        ("HIGH", "MEDIUM", Severity.MEDIUM),
        ("MEDIUM", "MEDIUM", Severity.MEDIUM),
        ("HIGH", "LOW", Severity.LOW),
        ("LOW", "HIGH", Severity.LOW),
    ],
)
def test_severity_combines_bandit_severity_and_confidence(
    severity: str, confidence: str, expected: Severity
) -> None:
    assert severity_for(severity, confidence) is expected


def test_parse_handles_missing_cwe_and_rejects_invalid_json(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    report = {
        "results": [
            {
                "filename": str(root / "a.py"),
                "test_id": "B999",
                "issue_text": "Custom issue",
                "issue_severity": "LOW",
                "issue_confidence": "LOW",
                "issue_cwe": {"id": 0},
                "line_number": 4,
                "line_range": [4, 6],
                "col_offset": 0,
            }
        ]
    }

    finding = parse_output(json.dumps(report), root)[0]

    assert (finding.start_line, finding.end_line, finding.cwe) == (4, 6, None)
    assert finding.confidence == pytest.approx(0.4)
    with pytest.raises(AnalyzerError):
        parse_output("{oops", root)
