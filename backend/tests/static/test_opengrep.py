import json
import re
from pathlib import Path

import pytest
import yaml

from app.errors import AnalyzerError, ToolUnavailableError
from app.findings import Category, Severity
from app.static.analyzers.opengrep import (
    RULES_DIRECTORY,
    OpengrepAnalyzer,
    find_executable,
    parse_output,
)
from tests.static.conftest import TargetFactory, by_rule

EXECUTABLE = find_executable()
requires_opengrep = pytest.mark.skipif(EXECUTABLE is None, reason="opengrep is not installed")

VULNERABLE_PYTHON = """
    import hashlib
    import os
    import random
    import subprocess
    import tempfile

    import jwt
    import requests
    import yaml


    def handler(name, cursor, app, blob, token_value, password):
        subprocess.run(f"ls {name}", shell=True)
        os.system("rm -rf " + name)
        cursor.execute(f"SELECT * FROM users WHERE id = {name}")
        yaml.load(blob)
        requests.get("https://example.com", verify=False)
        app.run(debug=True)
        hashlib.md5(password.encode())
        reset_token = random.randint(0, 999999)
        jwt.decode(token_value, options={"verify_signature": False})
        tempfile.mktemp()
        eval(name)
        return reset_token
"""

SAFE_PYTHON = """
    import hashlib
    import random
    import subprocess

    import yaml


    def handler(name, cursor, blob, data):
        subprocess.run(["ls", name])
        subprocess.run("ls -la", shell=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (name,))
        yaml.load(blob, Loader=yaml.SafeLoader)
        hashlib.sha256(data)
        eval("1 + 1")
        return random.choice([1, 2, 3])
"""

VULNERABLE_JAVASCRIPT = """
    const cp = require("child_process");
    function run(name, element, code) {
      cp.exec(`ls ${name}`);
      eval(code);
      element.innerHTML = name;
      element.innerHTML = "<b>static</b>";
    }
"""


# --- rule files (no binary needed) ---------------------------------------------------------------


def load_rules() -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for path in sorted(RULES_DIRECTORY.glob("*.yaml")):
        rules.extend(yaml.safe_load(path.read_text(encoding="utf-8"))["rules"])
    return rules


def test_every_rule_documents_cwe_category_and_confidence() -> None:
    rules = load_rules()

    assert len(rules) >= 10
    assert len({rule["id"] for rule in rules}) == len(rules)
    for rule in rules:
        metadata = rule["metadata"]
        assert isinstance(metadata, dict), rule["id"]
        assert re.fullmatch(r"CWE-\d+", str(metadata["cwe"])), rule["id"]
        assert metadata["category"] in {category.value for category in Category}, rule["id"]
        assert metadata["confidence"] in {"high", "medium", "low"}, rule["id"]
        assert rule["severity"] in {"ERROR", "WARNING", "INFO"}, rule["id"]


# --- parsing and availability (no binary needed) ----------------------------------------------


def test_parse_maps_severity_metadata_and_skips_paths_outside_root(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    report = {
        "results": [
            {
                "check_id": "python-sql-built-with-string-formatting",
                "path": str(root / "db.py"),
                "start": {"line": 4, "col": 5},
                "end": {"line": 4, "col": 40},
                "extra": {
                    "severity": "ERROR",
                    "message": "A SQL query is built with string formatting.  Use parameters.",
                    "metadata": {"cwe": "CWE-89", "category": "security", "confidence": "high"},
                },
            },
            {
                "check_id": "custom",
                "path": str(root / "a.py"),
                "start": {"line": 1, "col": 1},
                "end": {"line": 3, "col": 2},
                "extra": {"severity": "INFO", "message": "Note", "metadata": {"cwe": "n/a"}},
            },
            {
                "check_id": "custom",
                "path": str(tmp_path.parent / "outside.py"),
                "start": {"line": 1, "col": 1},
                "end": {"line": 1, "col": 2},
                "extra": {"severity": "ERROR", "message": "x", "metadata": {}},
            },
        ],
        "errors": [],
    }

    sql, note = parse_output(json.dumps(report), root)

    assert (sql.severity, sql.cwe, sql.confidence) == (Severity.HIGH, "CWE-89", 0.9)
    assert sql.title == "A SQL query is built with string formatting"
    assert (note.severity, note.cwe, note.end_column) == (Severity.LOW, None, None)
    with pytest.raises(AnalyzerError):
        parse_output("not json", root)


async def test_missing_binary_is_reported_as_unavailable(make_target: TargetFactory) -> None:
    target = make_target({"app.py": "x = 1\n"})

    with pytest.raises(ToolUnavailableError):
        await OpengrepAnalyzer(executable=None).analyze(target)


# --- real scans (binary needed; installed in CI) -----------------------------------------------


@requires_opengrep
async def test_rules_find_every_seeded_vulnerability(make_target: TargetFactory) -> None:
    target = make_target({"app/handler.py": VULNERABLE_PYTHON, "web/run.js": VULNERABLE_JAVASCRIPT})

    result = await OpengrepAnalyzer(EXECUTABLE).analyze(target)

    rules = {(f.file_path, f.rule_id) for f in result.findings}
    python_rules = {rule["id"] for rule in load_rules() if str(rule["id"]).startswith("python-")}
    javascript_rules = {
        rule["id"] for rule in load_rules() if str(rule["id"]).startswith("javascript-")
    }
    assert {rule for path, rule in rules if path == "app/handler.py"} == python_rules
    assert {rule for path, rule in rules if path == "web/run.js"} == javascript_rules
    assert by_rule(result.findings)["python-sql-built-with-string-formatting"].cwe == "CWE-89"


@requires_opengrep
async def test_safe_code_produces_no_findings(make_target: TargetFactory) -> None:
    target = make_target({"app/handler.py": SAFE_PYTHON})

    result = await OpengrepAnalyzer(EXECUTABLE).analyze(target)

    assert result.findings == []


@requires_opengrep
async def test_semgrepignore_inside_the_upload_cannot_hide_files(
    make_target: TargetFactory,
) -> None:
    target = make_target(
        {
            "app/handler.py": VULNERABLE_PYTHON,
            ".semgrepignore": "app/\n*.py\n",
            ".gitignore": "*\n",
        }
    )

    result = await OpengrepAnalyzer(EXECUTABLE).analyze(target)

    assert result.findings
