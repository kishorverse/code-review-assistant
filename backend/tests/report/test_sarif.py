import json
from pathlib import Path

from jsonschema import Draft4Validator

from app.findings import FindingStatus
from app.report.document import Report, set_finding_status
from app.report.sarif import FINGERPRINT_KEY, fingerprint, to_sarif

SCHEMA = json.loads(
    (Path(__file__).parent / "fixtures" / "sarif-schema-2.1.0.json").read_text(encoding="utf-8")
)


def test_output_is_valid_sarif_2_1_0(report: Report) -> None:
    log = to_sarif(report)

    errors = sorted(Draft4Validator(SCHEMA).iter_errors(log), key=lambda e: list(e.path))
    assert [error.message for error in errors] == []
    assert log["version"] == "2.1.0"


def test_maps_findings_to_rules_levels_and_locations(report: Report) -> None:
    run = to_sarif(report)["runs"][0]
    rules = {rule["id"]: rule for rule in run["tool"]["driver"]["rules"]}
    injection, division, dismissed = run["results"]

    assert list(rules) == ["B608", "ai/bug", "F401"]
    assert rules["B608"]["properties"] == {
        "tags": ["external/cwe/cwe-89", "security"],
        "security-severity": "7.5",
    }
    assert "security-severity" not in rules["ai/bug"]["properties"]
    assert (injection["level"], division["level"], dismissed["level"]) == (
        "error",
        "warning",
        "note",
    )
    location = injection["locations"][0]["physicalLocation"]
    assert location["artifactLocation"] == {"uri": "app/db.py", "uriBaseId": "%SRCROOT%"}
    assert location["region"]["startLine"] == 4
    assert location["region"]["snippet"]["text"].startswith("query = ")
    assert division["properties"]["verifiedBy"] == ["gemini"]
    assert division["properties"]["suggestion"] == "Guard against an empty list."
    assert run["results"][1]["ruleIndex"] == 1
    assert run["properties"]["grade"] == report.score.grade


def test_dismissed_and_rejected_findings_are_suppressed_and_unconfident_ones_left_out(
    report: Report,
) -> None:
    noted = report.model_copy(
        update={
            "findings": [
                report.findings[0].model_copy(update={"ai_note": "gemini could not confirm it."}),
                *report.findings[1:],
            ]
        }
    )
    rejected = set_finding_status(noted, report.findings[0].id, FindingStatus.REJECTED)

    results = to_sarif(rejected)["runs"][0]["results"]

    assert [r["ruleId"] for r in results] == ["B608", "ai/bug", "F401"]
    assert results[0]["suppressions"] == [
        {"kind": "external", "status": "accepted", "justification": "Rejected by a reviewer"}
    ]
    assert results[2]["suppressions"][0]["justification"] == "nvidia: used by a plugin."
    assert "suppressions" not in results[1]
    assert all(r["ruleId"] != "ai/style" for r in results)


def test_fingerprints_survive_line_changes_but_not_different_code(report: Report) -> None:
    injection = report.findings[0]
    moved = injection.model_copy(update={"start_line": 40, "end_line": 40})
    changed = injection.model_copy(update={"evidence": "cursor.execute(sql)"})

    assert fingerprint(moved) == fingerprint(injection)
    assert fingerprint(changed) != fingerprint(injection)
    results = to_sarif(report)["runs"][0]["results"]
    assert results[0]["partialFingerprints"] == {FINGERPRINT_KEY: fingerprint(injection)}
