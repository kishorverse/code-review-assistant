from pathlib import Path

import pytest

from app.errors import AnalyzerError
from app.findings import Category, Severity
from app.static.analyzers.radon import (
    RadonAnalyzer,
    complexity_findings,
    file_metrics,
    load_report,
    maintainability_findings,
)
from tests.static.conftest import TargetFactory


def branchy_function(name: str, branches: int) -> str:
    body = "".join(f"    if value == {n}:\n        return {n}\n" for n in range(branches))
    return f"def {name}(value):\n{body}    return -1\n"


async def test_flags_complex_functions_and_reports_file_metrics(
    make_target: TargetFactory,
) -> None:
    source = (
        "# Routing table.\n" + branchy_function("route", 35) + "\n\ndef simple():\n    return 1\n"
    )
    target = make_target({"app/router.py": source, "app/broken.py": "def oops(:\n"})

    result = await RadonAnalyzer().analyze(target)

    [finding] = [f for f in result.findings if f.rule_id == "cyclomatic-complexity"]
    assert (finding.file_path, finding.start_line) == ("app/router.py", 2)
    assert finding.severity is Severity.MEDIUM
    assert finding.category is Category.MAINTAINABILITY
    assert "route" in finding.title
    [metrics] = [m for m in result.metrics if m.path == "app/router.py"]
    assert metrics.lines == source.count("\n")
    assert metrics.comment_lines == 1
    assert metrics.maintainability_index is not None


async def test_configuration_inside_the_upload_is_not_applied(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {
            "app/router.py": branchy_function("route", 35),
            "setup.cfg": "[radon]\nexclude = *.py\ncc_min = F\n",
            "radon.cfg": "[radon]\nexclude = *.py\n",
        }
    )

    result = await RadonAnalyzer().analyze(target)

    assert any(f.rule_id == "cyclomatic-complexity" for f in result.findings)


def test_complexity_findings_cover_methods_and_skip_low_ranks(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    report = {
        str(root / "a.py"): [
            {
                "type": "class",
                "name": "Service",
                "rank": "C",
                "lineno": 1,
                "endline": 40,
                "complexity": 12,
                "methods": [
                    {
                        "type": "method",
                        "name": "handle",
                        "rank": "D",
                        "lineno": 3,
                        "endline": 30,
                        "complexity": 22,
                        "closures": [],
                    },
                    {
                        "type": "method",
                        "name": "ok",
                        "rank": "A",
                        "lineno": 31,
                        "endline": 33,
                        "complexity": 1,
                        "closures": [],
                    },
                ],
            }
        ],
        str(root / "broken.py"): {"error": "invalid syntax"},
    }

    findings = complexity_findings(report, root)

    assert [(f.start_line, f.severity) for f in findings] == [(3, Severity.LOW)]


def test_low_maintainability_index_is_reported_at_the_top_of_the_file(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    report = {
        str(root / "legacy.py"): {"mi": 12.4, "rank": "B"},
        str(root / "clean.py"): {"mi": 71.0, "rank": "A"},
        str(root / "broken.py"): {"error": "invalid syntax"},
    }

    [finding] = maintainability_findings(report, root)

    assert (finding.file_path, finding.start_line, finding.rule_id) == (
        "legacy.py",
        1,
        "maintainability-index",
    )


def test_file_metrics_skip_errors_and_join_maintainability(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    raw = {
        str(root / "a.py"): {
            "loc": 10,
            "lloc": 6,
            "sloc": 7,
            "comments": 1,
            "multi": 2,
            "blank": 1,
            "single_comments": 1,
        },
        str(root / "bad.py"): {"error": "invalid syntax"},
    }

    [metrics] = file_metrics(raw, {str(root / "a.py"): {"mi": 55.5, "rank": "A"}}, root)

    assert (metrics.path, metrics.source_lines, metrics.comment_lines) == ("a.py", 7, 3)
    assert metrics.maintainability_index == pytest.approx(55.5)


@pytest.mark.parametrize("stdout", ["not json", "[]"])
def test_invalid_reports_are_analyzer_errors(stdout: str) -> None:
    with pytest.raises(AnalyzerError):
        load_report(stdout)
