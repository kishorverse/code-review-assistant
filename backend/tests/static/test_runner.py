import asyncio
from pathlib import Path

from app.errors import AnalyzerError, ToolUnavailableError
from app.events import CollectingSink, FindingEvent, ToolEvent
from app.findings import REDACTED_EVIDENCE, Category, Finding, Severity
from app.static.base import (
    AnalysisTarget,
    AnalyzerResult,
    FileMetrics,
    FunctionMetrics,
    ToolStatus,
)
from app.static.runner import default_analyzers, merge_metrics, run_static_analysis
from tests.static.conftest import TargetFactory

CODE = "import os\n\n\ndef main():\n    return 1\n"


def issue(source: str, rule: str, line: int, severity: Severity, **extra: object) -> Finding:
    return Finding.model_validate(
        {
            "file_path": "app.py",
            "start_line": line,
            "end_line": line,
            "category": Category.BUG,
            "severity": severity,
            "title": rule,
            "message": rule,
            "rule_id": rule,
            "sources": [source],
            **extra,
        }
    )


class FakeAnalyzer:
    def __init__(self, name: str, outcome: object, applies: bool = True) -> None:
        self.name = name
        self._outcome = outcome
        self._applies = applies

    def applies_to(self, target: AnalysisTarget) -> bool:
        return self._applies

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        if self._outcome == "hang":
            await asyncio.sleep(10)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        assert isinstance(self._outcome, AnalyzerResult)
        return self._outcome


async def test_one_failing_tool_does_not_fail_the_scan(make_target: TargetFactory) -> None:
    target = make_target({"app.py": CODE})
    good = AnalyzerResult(
        findings=[
            issue("ruff", "F401", 1, Severity.LOW),
            issue("vulture", "unused-import", 1, Severity.LOW),
            issue("bandit", "B105", 4, Severity.HIGH, evidence=REDACTED_EVIDENCE),
        ]
    )
    analyzers = [
        FakeAnalyzer("good", good),
        FakeAnalyzer("broken", AnalyzerError("exited with code 2")),
        FakeAnalyzer("missing", ToolUnavailableError("opengrep is not installed")),
        FakeAnalyzer("buggy", RuntimeError("bug")),
        FakeAnalyzer("slow", "hang"),
        FakeAnalyzer("irrelevant", AnalyzerResult(), applies=False),
    ]
    sink = CollectingSink()

    result = await run_static_analysis(target, analyzers, sink, timeout_seconds=0.3)

    statuses = {run.tool: run.status for run in result.tool_runs}
    assert statuses == {
        "good": ToolStatus.OK,
        "broken": ToolStatus.FAILED,
        "missing": ToolStatus.SKIPPED,
        "buggy": ToolStatus.FAILED,
        "slow": ToolStatus.TIMED_OUT,
        "irrelevant": ToolStatus.SKIPPED,
    }
    assert [f.rule_id for f in result.findings] == ["B105", "F401"]
    assert result.findings[1].sources == ["ruff", "vulture"]
    assert result.findings[1].evidence == "import os"
    assert result.findings[0].evidence == REDACTED_EVIDENCE


async def test_emits_tool_events_and_final_findings(make_target: TargetFactory) -> None:
    target = make_target({"app.py": CODE})
    analyzer = FakeAnalyzer(
        "good", AnalyzerResult(findings=[issue("ruff", "E501", 4, Severity.LOW)])
    )
    sink = CollectingSink()

    await run_static_analysis(target, [analyzer], sink)

    tool_events = [e for e in sink.events if isinstance(e, ToolEvent)]
    assert [e.state for e in tool_events] == ["started", ToolStatus.OK]
    assert tool_events[1].finding_count == 1
    finding_events = [e for e in sink.events if isinstance(e, FindingEvent)]
    assert [e.finding.evidence for e in finding_events] == ["def main():"]


def test_merge_metrics_combines_partial_results_per_file() -> None:
    function = FunctionMetrics(
        name="main",
        start_line=4,
        end_line=5,
        cyclomatic_complexity=1,
        lines_of_code=2,
        parameters=0,
    )

    merged = merge_metrics(
        [
            FileMetrics(path="b.py", lines=5, maintainability_index=80.0),
            FileMetrics(path="a.py", lines=1),
            FileMetrics(path="b.py", functions=[function]),
        ]
    )

    assert [m.path for m in merged] == ["a.py", "b.py"]
    assert (merged[1].lines, merged[1].maintainability_index, merged[1].functions) == (
        5,
        80.0,
        [function],
    )


async def test_default_analyzers_run_end_to_end_on_a_real_project(
    make_target: TargetFactory, tmp_path: Path
) -> None:
    target = make_target(
        {
            "app/main.py": (
                "import os\nimport subprocess\n\n\n"
                "def run(name: str) -> int:\n"
                '    return subprocess.call("ls " + name, shell=True)\n'
            ),
            "web/index.js": "function hello(a) {\n  return a;\n}\n",
        }
    )

    result = await run_static_analysis(target, default_analyzers(), CollectingSink())

    assert {run.status for run in result.tool_runs} == {ToolStatus.OK}
    assert result.findings[0].rule_id == "B602"
    unused = next(f for f in result.findings if f.rule_id == "F401")
    assert set(unused.sources) == {"ruff", "vulture"}
    assert {m.path for m in result.metrics} >= {"app/main.py", "web/index.js"}
