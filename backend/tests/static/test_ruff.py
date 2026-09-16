import json
from pathlib import Path

import pytest

from app.errors import AnalyzerError
from app.findings import Category, Severity
from app.static.analyzers.ruff import RuffAnalyzer, classify, parse_output
from tests.static.conftest import TargetFactory, by_rule

SAMPLE = """
    import os


    def append(item, bucket=[]):
        try:
            bucket.append(item)
        except:
            pass
        return bucket
"""


async def test_reports_style_bug_and_maintainability_issues(make_target: TargetFactory) -> None:
    target = make_target({"pkg/app.py": SAMPLE, "web/app.js": "let x = 1;\n"})

    result = await RuffAnalyzer().analyze(target)

    findings = by_rule(result.findings)
    assert {"F401", "B006", "E722"} <= findings.keys()
    assert findings["F401"].file_path == "pkg/app.py"
    assert findings["F401"].start_line == 1
    assert findings["F401"].category is Category.MAINTAINABILITY
    assert findings["E722"].category is Category.BUG
    assert all(finding.sources == ["ruff"] for finding in result.findings)


@pytest.mark.parametrize(
    "hiding_config",
    [
        'extend-exclude = ["pkg"]\n',
        'include = ["nothing.py"]\n',
        '[lint.per-file-ignores]\n"*" = ["F401", "B006", "E722"]\n',
    ],
)
async def test_configuration_inside_the_upload_cannot_hide_findings(
    make_target: TargetFactory, hiding_config: str
) -> None:
    # Without --isolated each of these would silently remove every finding below.
    target = make_target({"pkg/app.py": SAMPLE, "ruff.toml": hiding_config})

    result = await RuffAnalyzer().analyze(target)

    assert {"F401", "B006", "E722"} <= by_rule(result.findings).keys()


@pytest.mark.parametrize(
    "ignore_files",
    [
        {".ignore": "*.py\n"},
        {".gitignore": "*\n", ".git/HEAD": "ref: refs/heads/main\n"},
    ],
    ids=["dot-ignore", "gitignore-in-repository"],
)
async def test_ignore_files_inside_the_upload_cannot_hide_code(
    make_target: TargetFactory, ignore_files: dict[str, str]
) -> None:
    # --isolated does not stop Ruff honoring .ignore and .gitignore files.
    target = make_target({"pkg/app.py": SAMPLE, **ignore_files})

    result = await RuffAnalyzer().analyze(target)

    assert {"F401", "B006", "E722"} <= by_rule(result.findings).keys()


def test_applies_only_to_python_projects(make_target: TargetFactory) -> None:
    assert not RuffAnalyzer().applies_to(make_target({"web/app.js": "let x;\n"}))


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("F821", (Category.BUG, Severity.HIGH)),
        ("F811", (Category.BUG, Severity.MEDIUM)),
        ("F401", (Category.MAINTAINABILITY, Severity.LOW)),
        ("E501", (Category.STYLE, Severity.LOW)),
        ("E902", (Category.BUG, Severity.HIGH)),
        ("W291", (Category.STYLE, Severity.INFO)),
        ("PERF401", (Category.PERFORMANCE, Severity.LOW)),
        (None, (Category.BUG, Severity.MEDIUM)),
    ],
)
def test_classifies_rules_by_most_specific_prefix(
    code: str | None, expected: tuple[Category, Severity]
) -> None:
    assert classify(code) == expected


def test_parse_skips_files_outside_the_root_and_handles_syntax_errors(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    output = json.dumps(
        [
            {
                "code": None,
                "filename": str(root / "broken.py"),
                "location": {"row": 3, "column": 5},
                "end_location": {"row": 4, "column": 1},
                "message": "SyntaxError: Expected an expression",
            },
            {
                "code": "E501",
                "filename": str(tmp_path.parent / "elsewhere.py"),
                "location": {"row": 1, "column": 80},
                "end_location": {"row": 1, "column": 90},
                "message": "Line too long (90 > 79)",
            },
        ]
    )

    findings = parse_output(output, root)

    assert len(findings) == 1
    assert findings[0].rule_id == "syntax-error"
    assert (findings[0].start_line, findings[0].end_line, findings[0].end_column) == (3, 4, None)


def test_parse_rejects_invalid_json(tmp_path: Path) -> None:
    with pytest.raises(AnalyzerError, match="invalid JSON"):
        parse_output("not json", tmp_path)
