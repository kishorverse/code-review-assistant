"""Versioned prompt templates for LLM review.

Prompts are Markdown files in this directory, rendered with Jinja2. Each one
that is sent as a prompt starts with a ``{# PROMPT_VERSION: n #}`` comment, and
review results record the versions used, so evaluation numbers stay tied to the
wording that produced them. Changing a prompt, or a partial it includes (files
starting with ``_``), means bumping the version of every prompt affected.
"""

import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.errors import ConfigError

PROMPTS_DIR = Path(__file__).parent
_VERSION = re.compile(r"\{#\s*PROMPT_VERSION:\s*(\S+)\s*#\}")


class PromptLibrary:
    """Renders prompt templates by name, such as ``"task_review"``."""

    def __init__(self, directory: Path = PROMPTS_DIR) -> None:
        self._directory = directory
        self._environment = Environment(
            loader=FileSystemLoader(directory, encoding="utf-8"),
            # Prompts are plain text: HTML escaping would corrupt code such as `a < b`.
            autoescape=select_autoescape(enabled_extensions=("html",), default=False),
            undefined=StrictUndefined,
        )

    def render(self, name: str, **values: object) -> str:
        """Render a prompt. Values are inserted as text and never evaluated as templates.

        Raises:
            jinja2.UndefinedError: If the prompt uses a value that was not given.
        """
        return self._environment.get_template(f"{name}.md").render(**values).strip()

    def version(self, name: str) -> str:
        """The ``PROMPT_VERSION`` a prompt declares.

        Raises:
            ConfigError: If the prompt has no version header.
        """
        source = (self._directory / f"{name}.md").read_text(encoding="utf-8")
        match = _VERSION.match(source)
        if match is None:
            raise ConfigError(f"prompt {name!r} has no PROMPT_VERSION header")
        return match.group(1)


@lru_cache
def default_prompts() -> PromptLibrary:
    """The prompts shipped with Margin."""
    return PromptLibrary()
