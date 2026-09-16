from pathlib import Path

from app.findings import Category, Severity
from app.static.analyzers.vulture import VultureAnalyzer, parse_output
from tests.static.conftest import TargetFactory, by_rule

SAMPLE = """
    import os
    import sys


    def check(value):
        return value
        print("never runs")


    print(sys.argv, check(1))
"""


async def test_reports_unused_imports_and_unreachable_code(make_target: TargetFactory) -> None:
    target = make_target({"tool/cli.py": SAMPLE, "tool/broken.py": "def oops(:\n"})

    result = await VultureAnalyzer().analyze(target)

    findings = by_rule(result.findings)
    assert set(findings) == {"unused-import", "unreachable-code"}
    assert (findings["unused-import"].file_path, findings["unused-import"].start_line) == (
        "tool/cli.py",
        1,
    )
    assert findings["unreachable-code"].start_line == 7
    assert all(f.category is Category.MAINTAINABILITY for f in result.findings)


async def test_pyproject_settings_inside_the_upload_are_not_applied(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {
            "tool/cli.py": SAMPLE,
            "pyproject.toml": '[tool.vulture]\nignore_names = ["os"]\nexclude = ["tool/"]\n',
        }
    )

    result = await VultureAnalyzer().analyze(target)

    assert "unused-import" in by_rule(result.findings)


def test_parse_handles_windows_paths_confidence_and_multi_line_ranges(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    output = "\n".join(
        [
            f"{root / 'a.py'}:4: unused import 'json' (90% confidence)",
            f"{root / 'a.py'}:10: unreachable code after 'return' (100% confidence, 3 lines)",
            f"{tmp_path.parent / 'outside.py'}:1: unused import 'x' (90% confidence)",
            "a.py:1: invalid syntax at line 1",
        ]
    )

    first, second = parse_output(output, root)

    assert (first.rule_id, first.confidence, first.title) == (
        "unused-import",
        0.9,
        "Unused import 'json'",
    )
    assert (second.start_line, second.end_line, second.severity) == (10, 12, Severity.LOW)
