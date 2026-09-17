import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from app.findings import Finding
from app.static.base import AnalysisTarget

TargetFactory = Callable[[dict[str, str]], AnalysisTarget]


@pytest.fixture
def make_target(tmp_path: Path) -> TargetFactory:
    """Write a small project and describe it the way the pipeline would."""

    def factory(files: dict[str, str]) -> AnalysisTarget:
        root = tmp_path / "source"
        scratch = tmp_path / "scratch"
        scratch.mkdir(exist_ok=True)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
        return AnalysisTarget(root=root.resolve(), files=tuple(sorted(files)), scratch=scratch)

    return factory


def by_rule(findings: list[Finding]) -> dict[str, Finding]:
    """Index findings by rule id; tests use unique rules per sample."""
    return {finding.rule_id or "": finding for finding in findings}
