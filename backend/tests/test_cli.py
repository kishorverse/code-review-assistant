import json
import zipfile
from pathlib import Path

import pytest
import respx
from jsonschema import Draft4Validator
from typer.testing import CliRunner

from app.cli import EXIT_CONFIG_ERROR, EXIT_FINDINGS_AT_THRESHOLD, EXIT_REJECTED, app
from app.config import Settings

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


def test_excluded_paths_are_not_scanned(project: Path) -> None:
    result = runner.invoke(
        app, ["scan", str(project), "--exclude", "app", "--format", "json", "--quiet"]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["summary"]["files_scanned"] == 0
    assert {"path": "app", "reason": "excluded"} in report["skipped_files"]


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


@pytest.fixture
def mock_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review with in-process models, never the keys in the developer's real .env."""
    monkeypatch.setattr("app.cli.get_settings", lambda: Settings(_env_file=None, llm_mode="mock"))


@pytest.mark.usefixtures("mock_models")
def test_review_uses_only_the_local_model_without_consent(project: Path) -> None:
    result = runner.invoke(app, ["scan", str(project), "--depth", "quick", "-f", "json", "-q"])

    assert result.exit_code == 0, result.output
    review = json.loads(result.stdout)["review"]
    assert review["depth"] == "quick"
    assert {call["provider"] for call in review["calls"]} == {"local"}
    assert review["summary"]["headline"] == "Mock summary: no model was called."
    assert review["stats"]["chunks_reviewed"] == 1
    assert review["prompt_versions"]["task_review"] == "1"


@pytest.mark.usefixtures("mock_models")
def test_allow_external_lets_hosted_providers_review(project: Path) -> None:
    result = runner.invoke(
        app, ["scan", str(project), "--depth", "quick", "--allow-external", "-f", "json", "-q"]
    )

    assert result.exit_code == 0, result.output
    calls = json.loads(result.stdout)["review"]["calls"]
    assert calls[0]["provider"] == "nvidia"


@pytest.mark.usefixtures("mock_models")
def test_table_output_summarizes_the_review(project: Path) -> None:
    result = runner.invoke(app, ["scan", str(project), "--depth", "quick", "-q"])

    assert result.exit_code == 0, result.output
    assert "AI review (quick): 1 chunks reviewed" in result.stdout
    assert "Summary: Mock summary: no model was called." in result.stdout


def test_review_without_configured_providers_warns_and_keeps_static_findings(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.cli.get_settings", lambda: Settings(_env_file=None))

    result = runner.invoke(app, ["scan", str(project), "--depth", "quick", "-f", "json"])

    assert result.exit_code == 0, result.output
    assert "No LLM providers are configured" in result.stderr
    report = json.loads(result.stdout)
    assert report["review"]["stats"]["tasks_failed"] == 1
    assert report["findings"][0]["rule_id"] == "B602"


def test_invalid_provider_config_exits_with_a_config_error(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "providers.yaml"
    monkeypatch.setattr(
        "app.cli.get_settings",
        lambda: Settings(_env_file=None, llm_mode="mock", providers_config_path=missing),
    )

    result = runner.invoke(app, ["scan", str(project), "--depth", "quick", "-q"])

    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "Configuration error" in result.stderr


def test_review_with_only_hosted_providers_needs_consent_and_sends_nothing(
    project: Path, monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    hosted_only = Settings(_env_file=None, gemini_api_key="placeholder", gemini_model="gemini-test")
    monkeypatch.setattr("app.cli.get_settings", lambda: hosted_only)

    result = runner.invoke(app, ["scan", str(project), "--depth", "quick", "-f", "json"])

    assert result.exit_code == 0, result.output
    assert "Pass --allow-external" in result.stderr
    assert not respx_mock.calls
    assert json.loads(result.stdout)["review"]["calls"] == []


def test_exports_sarif_and_html_reports(project: Path, tmp_path: Path) -> None:
    sarif_path, html_path = tmp_path / "margin.sarif", tmp_path / "report.html"

    sarif = runner.invoke(app, ["scan", str(project), "-f", "sarif", "-o", str(sarif_path), "-q"])
    html = runner.invoke(app, ["scan", str(project), "-f", "html", "-o", str(html_path), "-q"])

    assert (sarif.exit_code, html.exit_code) == (0, 0), sarif.output + html.output
    log = json.loads(sarif_path.read_text(encoding="utf-8"))
    schema_path = Path(__file__).parent / "report" / "fixtures" / "sarif-schema-2.1.0.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert list(Draft4Validator(schema).iter_errors(log)) == []
    assert "B602" in {result["ruleId"] for result in log["runs"][0]["results"]}
    page = html_path.read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert "<title>Margin review: project</title>" in page
