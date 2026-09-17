import json
from pathlib import Path

import pytest

from app.errors import AnalyzerError
from app.findings import Category
from app.static.analyzers.mypy import (
    MypyAnalyzer,
    mypy_command,
    parse_output,
    parseable_python_files,
)
from app.static.base import AnalysisTarget, run_tool
from tests.static.conftest import TargetFactory

TYPE_ERROR = "def label(count: int) -> str:\n    return count\n"


async def test_reports_type_errors_across_duplicate_module_names(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {
            "billing/utils.py": TYPE_ERROR,
            "shipping/utils.py": 'retries: int = "three"\n',
        }
    )

    result = await MypyAnalyzer().analyze(target)

    locations = {(f.file_path, f.start_line, f.rule_id) for f in result.findings}
    assert ("billing/utils.py", 2, "return-value") in locations
    assert ("shipping/utils.py", 1, "assignment") in locations
    assert all(f.category is Category.TYPING for f in result.findings)


async def test_broken_files_do_not_block_checking_the_rest(make_target: TargetFactory) -> None:
    target = make_target(
        {
            "app/broken.py": "def oops(:\n",
            "app/uses_broken.py": "from app.broken import oops\n\n" + TYPE_ERROR,
        }
    )

    result = await MypyAnalyzer().analyze(target)

    assert {(f.file_path, f.rule_id) for f in result.findings} == {
        ("app/uses_broken.py", "return-value")
    }


def plugin_project(make_target: TargetFactory, marker: Path) -> AnalysisTarget:
    plugin = (
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).touch()\n"
        "def plugin(version):\n"
        "    from mypy.plugin import Plugin\n"
        "    return Plugin\n"
    )
    return make_target(
        {
            "evil_plugin.py": plugin,
            "mypy.ini": "[mypy]\nplugins = evil_plugin.py\nignore_errors = True\n",
            "app.py": TYPE_ERROR,
        }
    )


async def test_plugins_configured_inside_the_upload_never_run(
    make_target: TargetFactory, tmp_path: Path
) -> None:
    marker = tmp_path / "PLUGIN_EXECUTED"
    target = plugin_project(make_target, marker)

    result = await MypyAnalyzer().analyze(target)

    assert not marker.exists()
    assert any(f.file_path == "app.py" for f in result.findings)


async def test_configuration_stays_disabled_even_when_run_from_the_project(
    make_target: TargetFactory, tmp_path: Path
) -> None:
    # The analyzer runs from the scratch directory; this checks the second, independent
    # defense by running the same command from inside the uploaded project.
    marker = tmp_path / "PLUGIN_EXECUTED"
    target = plugin_project(make_target, marker)
    argument_file = target.scratch / "files.txt"
    argument_file.write_text(str(target.root / "app.py") + "\n", encoding="utf-8")

    result = await run_tool(
        target, mypy_command(target, argument_file), accepted_exit_codes=(0, 1), cwd=target.root
    )

    assert not marker.exists()
    assert "return-value" in result.stdout


def test_parseable_files_excludes_syntax_errors_and_non_python(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {"ok.py": "x = 1\n", "bad.py": "x = (\n", "null.py": "x = 1\x00\n", "web.js": "x\n"}
    )

    assert parseable_python_files(target) == ["ok.py"]


def test_parse_keeps_errors_inside_the_root_only(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    lines = [
        {
            "file": str(root / "a.py"),
            "line": 3,
            "column": 4,
            "end_line": 3,
            "end_column": 9,
            "message": 'Name "x" is not defined',
            "code": "name-defined",
            "severity": "error",
        },
        {
            "file": str(root / "a.py"),
            "line": 3,
            "column": 4,
            "end_line": 3,
            "end_column": 9,
            "message": "See docs",
            "code": None,
            "severity": "note",
        },
        {
            "file": str(tmp_path.parent / "stub.py"),
            "line": 1,
            "column": 0,
            "end_line": 1,
            "end_column": 1,
            "message": "outside",
            "code": "misc",
            "severity": "error",
        },
        {
            "file": str(root / "b.py"),
            "line": -1,
            "column": -1,
            "end_line": -1,
            "end_column": 0,
            "message": "Duplicate module",
            "code": None,
            "severity": "error",
        },
    ]

    findings = parse_output("\n".join(json.dumps(line) for line in lines), root)

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.file_path, finding.start_line, finding.start_column) == ("a.py", 3, 5)
    assert finding.rule_id == "name-defined"
    with pytest.raises(AnalyzerError):
        parse_output("{not json", root)
