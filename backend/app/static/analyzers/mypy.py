"""mypy: type errors in Python.

Security: mypy configuration can load plugins, which are arbitrary Python
code, and mypy looks for configuration in the working directory and the home
directory. ``--config-file=`` (empty) disables every configuration file, so a
``mypy.ini`` or ``pyproject.toml`` inside an upload is never read.

Robustness: a single file with a syntax error stops mypy for the whole run, so
only files that parse are checked (Ruff reports the syntax errors). Uploads
often contain several ``utils.py`` files; ``MYPYPATH`` pointing at the root
with ``--explicit-package-bases`` keeps their module names distinct. The file
list goes through an argument file so large projects fit on any command line.
"""

import ast
import asyncio
import json
from pathlib import Path, PurePosixPath

from app.errors import AnalyzerError
from app.findings import Category, Finding, Severity, shorten_title
from app.static.base import (
    AnalysisTarget,
    AnalyzerResult,
    absolute_paths,
    relative_to_root,
    run_tool,
)
from app.static.process import python_tool

NAME = "mypy"
ARGUMENT_FILE = "mypy-files.txt"
CACHE_DIRECTORY = ".mypy_cache"


class MypyAnalyzer:
    """Type-checks the Python files that parse."""

    name = NAME

    def applies_to(self, target: AnalysisTarget) -> bool:
        """mypy only reviews Python."""
        return bool(target.files_with_suffix(".py"))

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        """Run mypy with configuration discovery disabled and normalize its JSON lines."""
        files = await asyncio.to_thread(parseable_python_files, target)
        if not files:
            return AnalyzerResult()
        argument_file = target.scratch / ARGUMENT_FILE
        await asyncio.to_thread(
            argument_file.write_text,
            "\n".join(absolute_paths(target, files)) + "\n",
            encoding="utf-8",
        )
        result = await run_tool(
            target,
            mypy_command(target, argument_file),
            accepted_exit_codes=(0, 1),
            extra_environment={"MYPYPATH": str(target.root)},
        )
        return AnalyzerResult(findings=parse_output(result.stdout, target.root))


def mypy_command(target: AnalysisTarget, argument_file: Path) -> list[str]:
    """The mypy command. Running from the scratch directory and ``--config-file=``
    are independent defenses against configuration inside the upload."""
    return python_tool(
        "mypy",
        "--config-file=",
        "--cache-dir",
        str(target.scratch / CACHE_DIRECTORY),
        "--ignore-missing-imports",
        "--follow-imports=skip",
        "--explicit-package-bases",
        "--no-error-summary",
        "--output",
        "json",
        f"@{argument_file}",
    )


def parseable_python_files(target: AnalysisTarget) -> list[str]:
    """Python files that compile to an AST. Parsing never executes the code."""
    parseable: list[str] = []
    for name in target.files_with_suffix(".py"):
        source = target.root.joinpath(*PurePosixPath(name).parts).read_bytes()
        try:
            ast.parse(source, filename=name)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            continue
        parseable.append(name)
    return parseable


def parse_output(stdout: str, root: Path) -> list[Finding]:
    """Normalize mypy's ``--output json`` lines; notes and project-level messages are dropped.

    Raises:
        AnalyzerError: If a line is not the expected JSON.
    """
    findings: list[Finding] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            error = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalyzerError("mypy produced invalid JSON") from exc
        path = relative_to_root(error["file"], root)
        if error["severity"] != "error" or error["line"] < 1 or path is None:
            continue
        message = error["message"]
        findings.append(
            Finding(
                file_path=path,
                start_line=error["line"],
                end_line=max(error.get("end_line", error["line"]), error["line"]),
                start_column=error["column"] + 1 if error["column"] >= 0 else None,
                end_column=error.get("end_column") or None,
                category=Category.TYPING,
                severity=Severity.MEDIUM,
                title=shorten_title(message),
                message=message,
                rule_id=error.get("code") or "type-error",
                sources=[NAME],
            )
        )
    return findings
