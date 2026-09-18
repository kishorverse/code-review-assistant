import json
from datetime import UTC, datetime
from pathlib import Path

from app.findings import Category, Finding, FindingStatus, Severity
from app.llm.models import CallRecord, CallStatus, Task
from evaluation.dataset import load_dataset
from evaluation.report import embed, evaluate, to_markdown
from evaluation.runner import FileRecord

LABELS = [
    {
        "id": "a/bug",
        "file": "a.py",
        "anchor": "return 1 / 0",
        "category": "bug",
        "severity": "high",
        "detection": "semantic",
        "description": "Division by zero.",
    },
    {
        "id": "b/bug",
        "file": "b.py",
        "anchor": "return 2 / 0",
        "category": "bug",
        "severity": "high",
        "detection": "semantic",
        "description": "Division by zero.",
    },
]


def dataset_at(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("def f():\n    return 1 / 0\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("def g():\n    return 2 / 0\n", encoding="utf-8")
    (root / "src" / "clean.py").write_text("X = 1\n", encoding="utf-8")
    spec = {"dataset": "tiny", "version": 1, "description": "t", "labels": LABELS}
    (root / "labels.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


def finding(file: str, line: int, *, sources: list[str], **changes: object) -> Finding:
    base = Finding(
        file_path=file,
        start_line=line,
        end_line=line,
        category=Category.BUG,
        severity=Severity.HIGH,
        title="Division by zero",
        message="Division by zero.",
        sources=sources,
        confidence=0.9,
    )
    return base.model_copy(update=changes)


def record(name: str, findings: list[Finding], *, complete: bool = True) -> FileRecord:
    return FileRecord(
        run="model-nvidia",
        file=name,
        started_at=datetime(2026, 9, 18, tzinfo=UTC),
        complete=complete,
        variants={"F-nvidia": findings},
        calls=[
            CallRecord(
                task=Task.REVIEW, provider="nvidia", model="m", status=CallStatus.OK, latency_ms=900
            )
        ],
        stats={"tasks_failed": 0 if complete else 1, "discarded": 0},
        durations_ms={"static": 1000, "review": 2000},
        models={"nvidia": "nemotron"},
        prompt_versions={},
    )


def test_only_complete_files_and_reported_findings_are_scored(tmp_path: Path) -> None:
    dataset = load_dataset(dataset_at(tmp_path / "data"))
    runs = tmp_path / "runs"
    runs.mkdir()
    records = [
        record("a.py", [finding("a.py", 2, sources=["nvidia"])]),
        # Its review failed: counting it would score the model as finding nothing.
        record("b.py", [], complete=False),
        record(
            "clean.py",
            [
                finding("clean.py", 1, sources=["nvidia"]),
                finding("clean.py", 1, sources=["nvidia"], confidence=0.3),
                finding("clean.py", 1, sources=["nvidia"], status=FindingStatus.REJECTED),
            ],
        ),
    ]
    (runs / "model-nvidia.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8"
    )

    [result] = evaluate(dataset, runs)

    card = result.scorecard
    assert (result.files, result.complete_files) == (3, 2)
    assert (card.overall.predictions, card.overall.labels, card.overall.found_labels) == (2, 1, 1)
    assert card.clean_file_findings == 1
    assert result.model_scorecard.overall.predictions == 2
    assert result.calls == {"nvidia": {"ok": 2}}
    assert result.file_seconds == (3.0, 3.0)
    table = to_markdown(dataset, [result])
    assert "| F-nvidia | `nemotron` | 2/3 | 2 | 0.50 | 1/1 |" in table
    assert "| a/bug | bug | semantic | ✓ |" in table


def test_verification_shows_whether_the_verifier_disputed_the_right_findings(
    tmp_path: Path,
) -> None:
    dataset = load_dataset(dataset_at(tmp_path / "data"))
    runs = tmp_path / "runs"
    runs.mkdir()
    real = finding("a.py", 2, sources=["nvidia"], verified_by=["local"])
    noise = finding(
        "clean.py",
        1,
        sources=["nvidia"],
        status=FindingStatus.NEEDS_REVIEW,
        ai_note="local disagreed: the value is constant.",
    )
    records = [
        record("a.py", [real]).model_copy(update={"variants": {"E-nvidia+local": [real]}}),
        record("clean.py", [noise]).model_copy(update={"variants": {"E-nvidia+local": [noise]}}),
    ]
    (runs / "verify.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8"
    )

    [result] = evaluate(dataset, runs)

    assert result.verification is not None
    assert (result.verification.confirmed, result.verification.confirmed_real) == (1, 1)
    assert (result.verification.disputed, result.verification.disputed_false) == (1, 1)
    assert result.scorecard.overall.precision == 0.5
    assert result.verification.precision_if_hidden == 1.0
    assert "| E-nvidia+local | 1 | 1 | 1 | 1 | 0.50 | 1.00 |" in to_markdown(dataset, [result])


def test_embedded_tables_are_replaced_and_everything_else_is_kept() -> None:
    document = (
        "Intro.\n\n<!-- TABLE:models -->\nold table\n<!-- /TABLE -->\n\nText.\n"
        "<!-- TABLE:cwe -->\n<!-- /TABLE -->\n"
    )

    updated = embed(document, {"models": "| new |\n", "cwe": "| cwe |"})

    assert updated == (
        "Intro.\n\n<!-- TABLE:models -->\n| new |\n<!-- /TABLE -->\n\nText.\n"
        "<!-- TABLE:cwe -->\n| cwe |\n<!-- /TABLE -->\n"
    )
    assert embed(updated, {"models": "| new |", "cwe": "| cwe |"}) == updated
