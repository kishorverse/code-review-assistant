import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import EXIT_FINDINGS_AT_THRESHOLD, EXIT_REJECTED, app

VULNERABLE = (
    "import os\nimport subprocess\n\n\n"
    "def run(name: str) -> int:\n"
    '    return subprocess.call("ls " + name, shell=True)\n'
)

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "app").mkdir(parents=True)
    (root / "app" / "tasks.py").write_text(VULNERABLE, encoding="utf-8")
    (root / "node_modules" / "dep").mkdir(parents=True)
    (root / "node_modules" / "dep" / "index.js").write_text("x = 1\n", encoding="utf-8")
    return root


def test_json_report_lists_findings_without_server_paths(project: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(project), "--format", "json", "--quiet"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["summary"]["files_scanned"] == 1
    assert report["findings"][0]["rule_id"] == "B602"
    assert {"path": "node_modules", "reason": "excluded_directory"} in report["skipped_files"]
    assert str(tmp_path) not in result.stdout


def test_fail_on_threshold_sets_the_exit_code(project: Path) -> None:
    failing = runner.invoke(app, ["scan", str(project), "--fail-on", "high", "--quiet"])
    passing = runner.invoke(app, ["scan", str(project), "--fail-on", "critical", "--quiet"])

    assert failing.exit_code == EXIT_FINDINGS_AT_THRESHOLD
    assert "B602" in failing.stdout
    assert passing.exit_code == 0


def test_scans_zip_archives_and_writes_output_files(tmp_path: Path) -> None:
    archive = tmp_path / "upload.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("pkg/tasks.py", VULNERABLE)
    output = tmp_path / "report.json"

    result = runner.invoke(
        app, ["scan", str(archive), "--format", "json", "--output", str(output), "--quiet"]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["findings"][0]["file_path"] == "pkg/tasks.py"


def test_rejected_archives_exit_with_a_clear_message(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.py", "print('x')\n")

    result = runner.invoke(app, ["scan", str(archive), "--quiet"])

    assert result.exit_code == EXIT_REJECTED
    assert "outside the project" in result.stderr
