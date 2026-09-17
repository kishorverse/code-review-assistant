from pathlib import Path

from app.events import CollectingSink, ScanStage, StageEvent
from app.findings import Category, Finding, Severity
from app.ingest.models import IngestLimits
from app.ingest.storage import ScanStorage, new_scan_id
from app.pipeline import directory_ingest, run_scan
from app.static.base import AnalysisTarget, AnalyzerResult


class RecordingAnalyzer:
    name = "recorder"

    def __init__(self) -> None:
        self.target: AnalysisTarget | None = None

    def applies_to(self, target: AnalysisTarget) -> bool:
        return True

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        self.target = target
        finding = Finding(
            file_path="app/main.py",
            start_line=1,
            end_line=1,
            category=Category.STYLE,
            severity=Severity.LOW,
            title="Example",
            message="Example",
            sources=[self.name],
        )
        return AnalyzerResult(findings=[finding])


async def test_runs_stages_in_order_and_hands_analyzers_the_ingested_files(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / "app").mkdir(parents=True)
    (project / "app" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    workspace = ScanStorage(tmp_path / "storage").create(new_scan_id())
    analyzer = RecordingAnalyzer()
    sink = CollectingSink()

    result = await run_scan(
        directory_ingest(project, IngestLimits()), workspace, sink, analyzers=[analyzer]
    )

    stages = [event.stage for event in sink.events if isinstance(event, StageEvent)]
    assert stages == [
        ScanStage.INGESTING,
        ScanStage.PREPROCESSING,
        ScanStage.ANALYZING,
        ScanStage.DONE,
    ]
    assert result.ingest.files == ["README.md", "app/main.py"]
    assert [file.path for file in result.files] == ["app/main.py"]
    assert analyzer.target is not None
    assert analyzer.target.scratch == workspace.scratch_dir
    assert analyzer.target.files == ("README.md", "app/main.py")
    assert result.static.findings[0].evidence == "print('hi')"
    assert set(result.stage_durations_ms) == {
        ScanStage.INGESTING,
        ScanStage.PREPROCESSING,
        ScanStage.ANALYZING,
    }
