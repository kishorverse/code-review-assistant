import hashlib
import json

from app.findings import Category, Severity
from app.preprocess.models import LineRange
from app.redaction import SecretIndex
from app.review.context import (
    MAX_STATIC_FINDINGS,
    build_context,
    describe_project,
    for_review,
    for_style,
    load_source,
)
from app.static.base import FileMetrics, FunctionMetrics
from tests.review.conftest import DB_MODULE, ProjectFactory, make_finding

# Masking matches values by hash, so any value works and none needs to look like a real token.
TOKEN = "placeholder-" + "credential"


def test_source_is_masked_and_numbered_like_the_chunks(make_project: ProjectFactory) -> None:
    root, [file] = make_project({"app/settings.py": f'DEBUG = False\nTOKEN = "{TOKEN}"\n'})
    index = SecretIndex()
    index.add_hashes([hashlib.sha1(TOKEN.encode(), usedforsecurity=False).hexdigest()])

    source = load_source(root, file, index)

    assert source.lines == ["DEBUG = False", 'TOKEN = "<REDACTED_SECRET_1>"']
    assert source.render([LineRange(start=2, end=2)]) == '2 | TOKEN = "<REDACTED_SECRET_1>"'
    assert source.excerpt(2, 2, padding=10).splitlines()[0] == "1 | DEBUG = False"


def test_context_shows_masked_code_and_the_chunks_static_findings(
    make_project: ProjectFactory,
) -> None:
    root, [file] = make_project({"app/db.py": DB_MODULE})
    source = load_source(root, file, SecretIndex())
    [chunk] = file.chunks
    injection = make_finding()
    unused = make_finding(
        start_line=1,
        category=Category.MAINTAINABILITY,
        severity=Severity.LOW,
        rule_id="F401",
        sources=["ruff"],
    )
    layout = make_finding(start_line=4, category=Category.STYLE, rule_id="E501", sources=["ruff"])
    elsewhere = make_finding(file_path="app/other.py")
    metrics = FileMetrics(
        path="app/db.py",
        maintainability_index=71.25,
        functions=[
            FunctionMetrics(
                name="find_user",
                start_line=3,
                end_line=5,
                cyclomatic_complexity=1,
                lines_of_code=3,
                parameters=2,
            )
        ],
    )

    context = build_context(
        chunk,
        source,
        [unused, layout, injection, elsewhere],
        metrics,
        "1 reviewable file",
        for_review,
    )

    assert context.static_findings == {"S1": injection, "S2": unused}
    shown = [json.loads(line) for line in context.prompt_values["static_findings"].splitlines()]
    assert shown[0] == {
        "id": "S1",
        "tool": "bandit",
        "rule": "B608",
        "category": "security",
        "severity": "medium",
        "lines": "4",
        "message": injection.message,
    }
    assert '"function": "find_user"' in context.prompt_values["metrics"]
    assert "maintainability index: 71.2" in context.prompt_values["metrics"]
    assert context.prompt_values["code"].startswith("1 | import sqlite3")
    assert context.prompt_values["partial_regions"] == "none"
    assert context.prompt_values["style_guide"] == "PEP 8 and PEP 257"


def test_style_task_sees_style_findings_and_formatting_rules_are_never_shown(
    make_project: ProjectFactory,
) -> None:
    root, [file] = make_project({"app/db.py": DB_MODULE})
    naming = make_finding(start_line=3, category=Category.STYLE, rule_id="N802", sources=["ruff"])
    layout = make_finding(start_line=4, category=Category.STYLE, rule_id="E501", sources=["ruff"])

    context = build_context(
        file.chunks[0],
        load_source(root, file, SecretIndex()),
        [naming, layout, make_finding()],
        None,
        "",
        for_style,
    )

    assert list(context.static_findings.values()) == [naming]
    assert context.prompt_values["metrics"] == "none"


def test_static_findings_are_capped_most_severe_first(make_project: ProjectFactory) -> None:
    root, [file] = make_project({"app/db.py": DB_MODULE})
    many = [make_finding(severity=Severity.LOW, rule_id=f"R{n}") for n in range(60)]
    critical = make_finding(severity=Severity.CRITICAL)

    context = build_context(
        file.chunks[0],
        load_source(root, file, SecretIndex()),
        [*many, critical],
        None,
        "",
        for_review,
    )

    assert len(context.static_findings) == MAX_STATIC_FINDINGS
    assert context.static_findings["S1"] is critical


def test_describe_project_counts_files_by_language(make_project: ProjectFactory) -> None:
    _, files = make_project({"a.py": "x = 1\n", "b.py": "y = 2\n", "c.js": "let z = 3;\n"})

    assert describe_project(files) == "3 reviewable files (python 2, javascript 1)"
    assert describe_project([]) == "no reviewable files"


def test_tool_messages_are_masked_like_the_code(make_project: ProjectFactory) -> None:
    root, [file] = make_project({"app/settings.py": f'TOKEN: str = "{TOKEN}"\n'})
    index = SecretIndex()
    index.add_hashes([hashlib.sha1(TOKEN.encode(), usedforsecurity=False).hexdigest()])
    quoting = make_finding(
        file_path="app/settings.py",
        start_line=1,
        category=Category.TYPING,
        rule_id="assignment",
        sources=["mypy"],
        message=f"Incompatible types (expression has type \"Literal['{TOKEN}']\")",
    )

    context = build_context(
        file.chunks[0], load_source(root, file, index), [quoting], None, "", for_review
    )

    assert TOKEN not in context.prompt_values["static_findings"]
    assert TOKEN not in context.prompt_values["code"]
    assert "<REDACTED_SECRET_1>" in context.prompt_values["static_findings"]
