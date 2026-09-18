from pathlib import Path

import pytest
from jinja2 import UndefinedError

from app.errors import ConfigError
from app.llm.prompts import PROMPTS_DIR, PromptLibrary, default_prompts

CONTEXT = {
    "project_summary": "3 files: python 3",
    "file_path": "app/db.py",
    "language": "python",
    "metrics": "none",
    "static_findings": "none",
    "partial_regions": "none",
}


def test_every_prompt_declares_a_version() -> None:
    prompts = [path.stem for path in PROMPTS_DIR.glob("*.md") if not path.name.startswith("_")]

    assert sorted(prompts) == [
        "system_reviewer",
        "system_summarizer",
        "system_verifier",
        "task_review",
        "task_style",
        "task_summarize",
        "task_verify",
    ]
    assert all(default_prompts().version(name) for name in prompts)


def test_code_is_inserted_verbatim_without_escaping_or_evaluation() -> None:
    code = "1 | if a < b and c > d: html = '<b>{{ user }}</b>'  # {% raw %} & {# note #}"

    rendered = default_prompts().render("task_review", code=code, **CONTEXT)

    assert code in rendered
    assert "PROMPT_VERSION" not in rendered
    assert rendered.endswith(code)


def test_style_prompt_names_the_style_guide() -> None:
    rendered = default_prompts().render(
        "task_style", style_guide="PEP 8 and PEP 257", code="1 | x = 1", **CONTEXT
    )

    assert "against PEP 8 and PEP 257." in rendered
    assert "File: app/db.py (python)" in rendered


def test_missing_values_are_an_error() -> None:
    with pytest.raises(UndefinedError):
        default_prompts().render("task_verify", file_path="a.py")


def test_prompt_without_a_version_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "task_new.md").write_text("TASK: do it\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="task_new"):
        PromptLibrary(tmp_path).version("task_new")


def test_models_are_told_that_masked_secrets_are_real() -> None:
    # A model once dismissed a hardcoded key as "a placeholder" because it only saw the mask.
    prompts = default_prompts()

    for name in ("system_reviewer", "system_verifier"):
        text = prompts.render(name)
        assert "<REDACTED_SECRET_1> are real secrets" in text
        rule = text.split("<REDACTED_SECRET_1>")[1].splitlines()[0]
        assert "not" in rule
