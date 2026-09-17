from app.findings import FindingStatus
from app.llm.models import CallRecord, CallStatus, Task
from app.report.document import Report, build_report, set_finding_status
from app.report.html import percentile, provider_usage, render_html
from tests.report.conftest import FINDINGS, GENERATED_AT, finding, scan_result


def test_renders_a_complete_standalone_page(report: Report) -> None:
    page = render_html(report)

    assert page.startswith("<!doctype html>")
    assert "<title>Margin review: shop.zip</title>" in page
    assert "One injection needs fixing." in page
    assert "<b>76</b>" in page
    assert "SQL built with string concatenation" in page
    assert "Verified by gemini" in page
    assert "Guard against an empty list." in page
    assert "nvidia: used by a plugin." in page
    assert "AI confidence 0.40 is below 0.6." in page
    assert "<code>app/db.py</code>" in page
    assert "task_review v1" in page
    assert "http://" not in page.replace("http://www.w3.org", "")
    assert "<script" not in page.lower()


def test_escapes_code_and_model_output() -> None:
    hostile = finding(
        title="<script>alert(1)</script>",
        evidence='html = "<img src=x onerror=alert(2)>"',
        suggestion="Use </pre><b>bold</b>",
    )
    report = build_report(
        scan_result([hostile], reviewed=False),
        source="<i>x</i>.zip",
        min_confidence=0.6,
        generated_at=GENERATED_AT,
    )

    page = render_html(report)

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<img src=x" not in page
    assert "</pre><b>bold</b>" not in page
    assert "<i>x</i>" not in page


def test_static_reports_have_no_model_sections() -> None:
    report = build_report(
        scan_result(FINDINGS[:1], reviewed=False),
        source="src",
        min_confidence=0.6,
        generated_at=GENERATED_AT,
    )

    page = render_html(report)

    assert "static analysis only" in page
    assert "Models and provenance" not in page
    assert "Executive summary" not in page


def test_rejected_findings_move_to_not_counted(report: Report) -> None:
    rejected = set_finding_status(report, report.findings[0].id, FindingStatus.REJECTED)

    page = render_html(rejected)

    assert "Rejected by a reviewer." in page


def test_provider_usage_counts_attempts_and_files_that_received_code() -> None:
    calls = [
        CallRecord(
            task=Task.REVIEW,
            provider="nvidia",
            model="m",
            status=CallStatus.OK,
            latency_ms=100,
            file_path="a.py",
        ),
        CallRecord(
            task=Task.REVIEW,
            provider="nvidia",
            model="m",
            status=CallStatus.OK,
            latency_ms=300,
            file_path="b.py",
        ),
        CallRecord(
            task=Task.REVIEW,
            provider="nvidia",
            model="m",
            status=CallStatus.UNAVAILABLE,
            file_path="c.py",
        ),
        CallRecord(
            task=Task.REVIEW,
            provider="gemini",
            model="g",
            status=CallStatus.SKIPPED,
            file_path="d.py",
        ),
        CallRecord(
            task=Task.REVIEW,
            provider="local",
            model="q",
            status=CallStatus.CACHED,
            file_path="e.py",
        ),
    ]

    [nvidia] = provider_usage(calls)

    assert (nvidia.answered, nvidia.failed, nvidia.p50_ms, nvidia.p95_ms) == (2, 1, 100, 300)
    assert nvidia.files == ["a.py", "b.py", "c.py"]


def test_percentile_uses_nearest_rank() -> None:
    values = list(range(1, 101))

    assert (percentile(values, 50), percentile(values, 95), percentile([], 50)) == (50, 95, 0)
