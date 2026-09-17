import asyncio

from app.events import ScanStatus, StatusEvent
from app.findings import Category, Finding, Severity
from app.scans.manager import ScanManager
from app.static.base import AnalysisTarget, AnalyzerResult

SOURCE = "def average(values):\n    return sum(values) / len(values)\n"


class FlagEveryFile:
    """A fast analyzer that reports one finding per file, optionally waiting for a signal."""

    name = "flagger"

    def __init__(self, gate: asyncio.Event | None = None) -> None:
        self.gate = gate

    def applies_to(self, target: AnalysisTarget) -> bool:
        return True

    async def analyze(self, target: AnalysisTarget) -> AnalyzerResult:
        if self.gate is not None:
            await self.gate.wait()
        return AnalyzerResult(
            findings=[
                Finding(
                    file_path=path,
                    start_line=2,
                    end_line=2,
                    category=Category.BUG,
                    severity=Severity.MEDIUM,
                    title="Possible division by zero",
                    message="len(values) may be zero.",
                    sources=[self.name],
                )
                for path in target.files
            ]
        )


async def wait_for_status(manager: ScanManager, scan_id: str, status: ScanStatus) -> None:
    """Follow the scan's events until it reports a status, instead of sleeping for a guess."""
    log = await manager.events(scan_id)
    async with asyncio.timeout(10):
        async for stored in log.follow():
            if isinstance(stored.event, StatusEvent) and stored.event.status is status:
                return
    raise AssertionError(f"the scan finished without reaching {status.value}")
