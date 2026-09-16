import json
from pathlib import Path

import pytest

from app.errors import AnalyzerError
from app.findings import REDACTED_EVIDENCE, Severity
from app.static.analyzers.detect_secrets import DetectSecretsAnalyzer, parse_output
from tests.static.conftest import TargetFactory, by_rule

# Assembled at runtime so this repository never contains a secret-shaped literal.
AWS_ACCESS_KEY = "AKIA" + "IOSFODNN7" + "EXAMPLE"
LOGIN_VALUE = "tr0ub4dor" + "-and-3-more"


async def test_finds_secrets_in_any_file_and_never_echoes_them(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {
            "config/settings.py": f'AWS_KEY = "{AWS_ACCESS_KEY}"\n',
            "deploy/app.yaml": f"db:\n  password: {LOGIN_VALUE}\n",
        }
    )

    result = await DetectSecretsAnalyzer().analyze(target)

    findings = by_rule(result.findings)
    aws = findings["AWS Access Key"]
    assert (aws.file_path, aws.start_line, aws.severity, aws.cwe) == (
        "config/settings.py",
        1,
        Severity.HIGH,
        "CWE-798",
    )
    assert findings["Secret Keyword"].file_path == "deploy/app.yaml"
    for finding in result.findings:
        assert finding.evidence == REDACTED_EVIDENCE
        assert AWS_ACCESS_KEY not in finding.message + finding.title
        assert LOGIN_VALUE not in finding.message + finding.title


def test_parse_scores_heuristic_detectors_lower_and_rejects_bad_reports(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    report = {
        "results": {
            "a.py": [
                {"type": "Private Key", "line_number": 2, "hashed_secret": "x"},
                {"type": "Hex High Entropy String", "line_number": 9, "hashed_secret": "y"},
            ]
        }
    }

    key, entropy = parse_output(json.dumps(report), root)

    assert (key.confidence, entropy.confidence) == (0.9, 0.6)
    with pytest.raises(AnalyzerError):
        parse_output("{}", root)
