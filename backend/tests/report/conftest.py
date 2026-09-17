from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.events import ScanStage
from app.findings import Category, Finding, FindingStatus, Severity
from app.ingest.models import IngestResult, SkippedFile, SkipReason
from app.languages.base import SupportLevel
from app.llm.models import CallRecord, CallStatus, Task
from app.pipeline import ScanResult
from app.preprocess.models import PreprocessedFile
from app.redaction import SecretIndex
from app.report.document import Report, build_report
from app.review.answers import ReviewSummary
from app.review.planner import Depth
from app.review.session import ReviewResult, ReviewStats
from app.static.base import FileMetrics, FunctionMetrics, ToolRun, ToolStatus
from app.static.runner import StaticAnalysisResult

GENERATED_AT = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "file_path": "app/db.py",
        "start_line": 4,
        "category": Category.SECURITY,
        "severity": Severity.HIGH,
        "title": "SQL built with string concatenation",
        "message": "User input reaches the query.",
        "rule_id": "B608",
        "sources": ["bandit"],
        "evidence": 'query = "SELECT * FROM users WHERE name = \'" + name',
        "cwe": "CWE-89",
    }
    values.update(overrides)
    values.setdefault("end_line", values["start_line"])
    return Finding.model_validate(values)


FINDINGS = [
    finding(),
    finding(
        start_line=9,
        severity=Severity.MEDIUM,
        category=Category.BUG,
        rule_id="ai/bug",
        sources=["nvidia"],
        verified_by=["gemini"],
        title="Division by zero",
        cwe=None,
        confidence=0.9,
        suggestion="Guard against an empty list.",
    ),
    finding(
        start_line=1,
        severity=Severity.LOW,
        category=Category.MAINTAINABILITY,
        rule_id="F401",
        sources=["ruff"],
        title="Unused import",
        status=FindingStatus.DISMISSED_BY_AI,
        ai_note="nvidia: used by a plugin.",
        cwe=None,
    ),
    finding(
        start_line=12,
        severity=Severity.LOW,
        category=Category.STYLE,
        rule_id="ai/style",
        sources=["hf-small"],
        title="Vague name",
        confidence=0.4,
        cwe=None,
    ),
]


def scan_result(findings: list[Finding] | None = None, reviewed: bool = True) -> ScanResult:
    files = [
        PreprocessedFile(
            path="app/db.py",
            language="python",
            support=SupportLevel.FULL,
            line_count=40,
            partial_regions=[],
            chunks=[],
        )
    ]
    metrics = [
        FileMetrics(
            path="app/db.py",
            source_lines=30,
            maintainability_index=65.0,
            functions=[
                FunctionMetrics(
                    name="find_user",
                    start_line=3,
                    end_line=20,
                    cyclomatic_complexity=24,
                    lines_of_code=18,
                    parameters=2,
                ),
                FunctionMetrics(
                    name="average",
                    start_line=22,
                    end_line=24,
                    cyclomatic_complexity=1,
                    lines_of_code=3,
                    parameters=1,
                ),
            ],
        )
    ]
    findings = FINDINGS if findings is None else findings
    static = StaticAnalysisResult(
        findings=[f for f in findings if "bandit" in f.sources or "ruff" in f.sources],
        tool_runs=[ToolRun(tool="bandit", status=ToolStatus.OK, duration_ms=500, finding_count=1)],
        metrics=metrics,
        secrets=SecretIndex(),
    )
    review = None
    if reviewed:
        review = ReviewResult(
            depth=Depth.STANDARD,
            findings=findings,
            calls=[
                CallRecord(
                    task=Task.REVIEW,
                    provider="nvidia",
                    model="nemotron",
                    status=CallStatus.OK,
                    latency_ms=3400,
                    file_path="app/db.py",
                ),
                CallRecord(
                    task=Task.VERIFY,
                    provider="gemini",
                    model="flash",
                    status=CallStatus.UNAVAILABLE,
                    latency_ms=900,
                    detail="HTTP 503",
                    file_path="app/db.py",
                ),
                CallRecord(
                    task=Task.SUMMARIZE,
                    provider="gemini",
                    model="flash",
                    status=CallStatus.OK,
                    latency_ms=2100,
                ),
            ],
            summary=ReviewSummary(headline="One injection needs fixing.", strengths=["Small"]),
            stats=ReviewStats(chunks_reviewed=1, ai_findings=2, verified=1),
            prompt_versions={"task_review": "1"},
        )
    return ScanResult(
        ingest=IngestResult(
            root=Path("/srv/margin/storage/secret-location"),
            files=["README.md", "app/db.py"],
            skipped=[SkippedFile(path="node_modules", reason=SkipReason.EXCLUDED_DIRECTORY)],
        ),
        files=files,
        static=static,
        stage_durations_ms={ScanStage.ANALYZING: 1200},
        findings=findings,
        review=review,
    )


@pytest.fixture
def report() -> Report:
    return build_report(
        scan_result(), source="shop.zip", min_confidence=0.6, generated_at=GENERATED_AT
    )
