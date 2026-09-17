from app.findings import REDACTED_EVIDENCE, Category, Finding, Severity
from app.static.evidence import MAX_EVIDENCE_LINES, attach_evidence
from tests.static.conftest import TargetFactory


def at(file_path: str, start: int, end: int, **extra: object) -> Finding:
    return Finding.model_validate(
        {
            "file_path": file_path,
            "start_line": start,
            "end_line": end,
            "category": Category.STYLE,
            "severity": Severity.LOW,
            "title": "t",
            "message": "m",
            "sources": ["ruff"],
            **extra,
        }
    )


def test_fills_evidence_from_file_lines_and_caps_long_ranges(make_target: TargetFactory) -> None:
    body = "".join(f"line {n}   \r\n" for n in range(1, 21))
    target = make_target({"pkg/long.py": body})

    short, long = attach_evidence([at("pkg/long.py", 2, 3), at("pkg/long.py", 1, 20)], target.root)

    assert short.evidence == "line 2\nline 3"
    assert long.evidence is not None
    assert len(long.evidence.splitlines()) == MAX_EVIDENCE_LINES


def test_keeps_existing_and_redacted_evidence_and_tolerates_missing_files(
    make_target: TargetFactory,
) -> None:
    target = make_target({"a.py": "x = 1\n\n"})
    findings = [
        at("a.py", 1, 1, evidence=REDACTED_EVIDENCE),
        at("missing.py", 1, 1),
        at("a.py", 2, 2),
    ]

    redacted, missing, blank = attach_evidence(findings, target.root)

    assert redacted.evidence == REDACTED_EVIDENCE
    assert missing.evidence is None
    assert blank.evidence is None
