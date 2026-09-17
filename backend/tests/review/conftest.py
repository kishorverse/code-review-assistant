import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from app.findings import Category, Finding, Severity
from app.languages.registry import default_registry
from app.preprocess.models import ChunkingConfig, PreprocessedFile
from app.preprocess.source_file import preprocess_file
from app.review.answers import ReportedIssue

ProjectFactory = Callable[[dict[str, str]], tuple[Path, list[PreprocessedFile]]]


@pytest.fixture
def make_project(tmp_path: Path) -> ProjectFactory:
    """Write files and preprocess them the way the pipeline does."""

    def factory(files: dict[str, str]) -> tuple[Path, list[PreprocessedFile]]:
        root = tmp_path / "source"
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(textwrap.dedent(content).lstrip("\n").encode("utf-8"))
        registry = default_registry()
        processed = [
            preprocess_file(root, name, registry, ChunkingConfig()) for name in sorted(files)
        ]
        return root, [file for file in processed if file is not None]

    return factory


def make_finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "file_path": "app/db.py",
        "start_line": 4,
        "category": Category.SECURITY,
        "severity": Severity.MEDIUM,
        "title": "SQL built with string concatenation",
        "message": "Possible SQL injection vector through string-based query construction.",
        "rule_id": "B608",
        "sources": ["bandit"],
    }
    values.update(overrides)
    values.setdefault("end_line", values["start_line"])
    return Finding.model_validate(values)


def make_issue(**overrides: object) -> ReportedIssue:
    values: dict[str, object] = {
        "start_line": 4,
        "category": "security",
        "severity": "high",
        "title": "SQL injection",
        "message": "name is concatenated into the query.",
        "evidence": 'query = "SELECT * FROM users WHERE name = \'" + name',
        "confidence": 0.9,
    }
    values.update(overrides)
    values.setdefault("end_line", values["start_line"])
    return ReportedIssue.model_validate(values)


DB_MODULE = """
    import sqlite3

    def find_user(db, name):
        query = "SELECT * FROM users WHERE name = '" + name + "'"
        return db.execute(query).fetchall()
"""
