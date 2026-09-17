import json

import pytest

from app.findings import FindingStatus
from app.report.document import Report, UnknownFindingError, build_report, set_finding_status
from tests.report.conftest import GENERATED_AT, scan_result


def test_counts_only_reported_findings(report: Report) -> None:
    counts = report.summary

    assert (counts.files_scanned, counts.files_reviewed, counts.findings) == (2, 1, 2)
    assert report.scanned_files == ["README.md", "app/db.py"]
    assert counts.by_severity == {"high": 1, "medium": 1}
    assert counts.by_category == {"security": 1, "bug": 1}
    assert counts.not_reported.model_dump() == {
        "dismissed_by_ai": 1,
        "rejected": 0,
        "below_min_confidence": 1,
    }
    assert [f.title for f in report.reported_findings()] == [
        "SQL built with string concatenation",
        "Division by zero",
    ]


def test_scores_from_reported_findings_and_measured_lines(report: Report) -> None:
    # 30 measured source lines -> KLOC below 1; high 10 + medium 4; 1 of 2 functions >= 21.
    assert (report.score.finding_penalty, report.score.complexity_penalty) == (14.0, 10.0)
    assert (report.score.score, report.score.grade) == (76, "B")


def test_keeps_review_provenance_and_never_server_paths(report: Report) -> None:
    document = report.model_dump_json()

    assert report.review is not None
    assert report.review.summary is not None
    assert report.review.summary.headline == "One injection needs fixing."
    assert report.review.stats["verified"] == 1
    assert [call.file_path for call in report.review.calls] == ["app/db.py", "app/db.py", None]
    assert "secret-location" not in document
    assert json.loads(document)["source"] == "shop.zip"


def test_static_only_scans_have_no_review_section() -> None:
    report = build_report(
        scan_result(reviewed=False), source="src", min_confidence=0.6, generated_at=GENERATED_AT
    )

    assert report.review is None


def test_reviewer_decisions_update_counts_and_score(report: Report) -> None:
    injection, _, dismissed, _ = report.findings

    rejected = set_finding_status(report, injection.id, FindingStatus.REJECTED)
    restored = set_finding_status(rejected, dismissed.id, FindingStatus.OPEN)
    accepted = set_finding_status(restored, injection.id, FindingStatus.ACCEPTED)

    assert (rejected.summary.findings, rejected.summary.not_reported.rejected) == (1, 1)
    assert rejected.score.score > report.score.score
    assert restored.summary.not_reported.dismissed_by_ai == 0
    assert restored.summary.findings == 2
    assert accepted.summary.findings == 3
    assert accepted.findings[0].status is FindingStatus.ACCEPTED
    assert report.findings[0].status is FindingStatus.OPEN


def test_reviewers_cannot_set_ai_statuses_or_unknown_findings(report: Report) -> None:
    with pytest.raises(ValueError, match="cannot set"):
        set_finding_status(report, report.findings[0].id, FindingStatus.DISMISSED_BY_AI)
    with pytest.raises(UnknownFindingError):
        set_finding_status(report, "0" * 32, FindingStatus.ACCEPTED)


def test_round_trips_through_json(report: Report) -> None:
    assert Report.model_validate_json(report.model_dump_json()) == report
