import asyncio
import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.errors import (
    FileNotInScanError,
    IngestError,
    ScanNotFinishedError,
    ScanNotFoundError,
    ScanQueueFullError,
    UnknownFindingError,
)
from app.events import ScanStatus, StatusEvent
from app.findings import FindingStatus
from app.ingest.storage import ScanStorage
from app.llm.models import LLMRequest
from app.llm.providers.mock import MockProvider
from app.llm.router import Router
from app.review.planner import Depth, ReviewOptions
from app.scans.manager import INTERRUPTED_MESSAGE, ScanManager, display_name
from tests.review.conftest import mock_router
from tests.scans.fakes import SOURCE, FlagEveryFile, wait_for_status


def make_manager(
    root: Path,
    router: Router | None = None,
    analyzer: FlagEveryFile | None = None,
    max_concurrent: int = 2,
    now: datetime | None = None,
) -> ScanManager:
    analyzer = analyzer or FlagEveryFile()
    return ScanManager(
        ScanStorage(root),
        router=router or mock_router(MockProvider("local")),
        analyzers=lambda: [analyzer],
        retention=timedelta(hours=24),
        max_concurrent=max_concurrent,
        now=(lambda: now) if now else lambda: datetime.now(UTC),
    )


async def submit(
    manager: ScanManager,
    content: bytes = SOURCE.encode(),
    filename: str = "stats.py",
    options: ReviewOptions | None = None,
) -> str:
    workspace = await manager.new_workspace()
    manager.upload_path(workspace).write_bytes(content)
    info = await manager.submit(workspace, filename, options or ReviewOptions(depth=Depth.STATIC))
    return info.id


async def finish(manager: ScanManager, scan_id: str) -> list[object]:
    """Wait for a scan to finish and return all of its events."""
    log = await manager.events(scan_id)

    async def collect() -> list[object]:
        return [stored.event async for stored in log.follow()]

    return await asyncio.wait_for(collect(), timeout=10)


async def test_runs_a_scan_and_keeps_its_report_and_events(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    scan_id = await submit(manager, options=ReviewOptions(depth=Depth.QUICK))
    events = await finish(manager, scan_id)

    info = await manager.info(scan_id)
    assert (info.status, info.source, info.depth) == (ScanStatus.DONE, "stats.py", Depth.QUICK)
    assert info.started_at is not None and info.finished_at is not None
    statuses = [e.status for e in events if isinstance(e, StatusEvent)]
    assert statuses == [ScanStatus.QUEUED, ScanStatus.RUNNING, ScanStatus.DONE]
    report = await manager.report(scan_id)
    assert [f.title for f in report.findings] == ["Possible division by zero"]
    assert report.review is not None
    assert report.source == "stats.py"
    assert await manager.read_file(scan_id, "stats.py") == SOURCE


async def test_a_rejected_upload_raises_and_leaves_nothing_behind(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.py", "x = 1\n")

    with pytest.raises(IngestError):
        await submit(manager, archive.getvalue(), "evil.zip")

    assert list(tmp_path.iterdir()) == []


async def test_scans_beyond_the_limit_wait_in_the_queue(tmp_path: Path) -> None:
    gate = asyncio.Event()
    manager = make_manager(tmp_path, analyzer=FlagEveryFile(gate), max_concurrent=1)

    first = await submit(manager)
    second = await submit(manager)
    await wait_for_status(manager, first, ScanStatus.RUNNING)

    assert (await manager.info(second)).status is ScanStatus.QUEUED
    gate.set()
    await finish(manager, first)
    await finish(manager, second)
    assert (await manager.info(second)).status is ScanStatus.DONE


async def test_an_unexpected_error_fails_only_that_scan(tmp_path: Path) -> None:
    def broken(request: LLMRequest) -> str:
        raise RuntimeError("provider bug")

    manager = make_manager(tmp_path, router=mock_router(MockProvider("local", respond=broken)))

    scan_id = await submit(manager, options=ReviewOptions(depth=Depth.QUICK))
    events = await finish(manager, scan_id)

    info = await manager.info(scan_id)
    assert (info.status, info.error) == (ScanStatus.FAILED, "The scan failed unexpectedly.")
    assert events[-1] == StatusEvent(status=ScanStatus.FAILED, message=info.error)
    with pytest.raises(ScanNotFinishedError):
        await manager.report(scan_id)


async def test_finished_scans_and_decisions_survive_a_restart(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    scan_id = await submit(manager)
    await finish(manager, scan_id)
    finding = (await manager.report(scan_id)).findings[0]
    await manager.set_finding_status(scan_id, finding.id, FindingStatus.REJECTED)

    restarted = make_manager(tmp_path)

    report = await restarted.report(scan_id)
    assert report.findings[0].status is FindingStatus.REJECTED
    assert report.summary.not_reported.rejected == 1
    assert (await restarted.info(scan_id)).status is ScanStatus.DONE
    assert len(await finish(restarted, scan_id)) > 3


async def test_a_scan_running_during_a_restart_is_marked_interrupted(tmp_path: Path) -> None:
    gate = asyncio.Event()
    manager = make_manager(tmp_path, analyzer=FlagEveryFile(gate))
    scan_id = await submit(manager)
    await wait_for_status(manager, scan_id, ScanStatus.RUNNING)

    restarted = make_manager(tmp_path)
    info = await restarted.info(scan_id)

    assert (info.status, info.error) == (ScanStatus.FAILED, INTERRUPTED_MESSAGE)
    await manager.close()


async def test_reviewer_decisions_are_validated(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    scan_id = await submit(manager)
    await finish(manager, scan_id)

    with pytest.raises(UnknownFindingError):
        await manager.set_finding_status(scan_id, "f" * 32, FindingStatus.ACCEPTED)


async def test_only_the_scans_own_files_can_be_read(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    scan_id = await submit(manager)
    await finish(manager, scan_id)

    for path in ("../stats.py", "results/scan.json", "other.py"):
        with pytest.raises(FileNotInScanError):
            await manager.read_file(scan_id, path)


async def test_unknown_and_malformed_ids_are_not_found(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    for scan_id in ("0" * 32, "../../etc", "not-a-scan"):
        with pytest.raises(ScanNotFoundError):
            await manager.info(scan_id)


async def test_deleting_a_running_scan_stops_it_and_removes_its_files(tmp_path: Path) -> None:
    gate = asyncio.Event()
    manager = make_manager(tmp_path, analyzer=FlagEveryFile(gate))
    scan_id = await submit(manager)
    await wait_for_status(manager, scan_id, ScanStatus.RUNNING)

    await manager.delete(scan_id)

    assert not (tmp_path / scan_id).exists()
    with pytest.raises(ScanNotFoundError):
        await manager.info(scan_id)


async def test_expired_scans_are_purged(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    scan_id = await submit(manager)
    await finish(manager, scan_id)

    later = make_manager(tmp_path, now=datetime.now(UTC) + timedelta(hours=25))
    removed = await later.purge_expired()

    assert removed == [scan_id]
    assert not (tmp_path / scan_id).exists()


def test_display_names_are_short_printable_base_names() -> None:
    assert display_name("C:\\Users\\me\\project.zip") == "project.zip"
    assert display_name("dir/evil" + chr(0x202E) + "name.py" + chr(10)) == "evilname.py"
    assert display_name("") == "upload"
    assert len(display_name("a" * 500 + ".py")) == 120


async def test_new_uploads_are_refused_while_too_many_scans_are_pending(tmp_path: Path) -> None:
    gate = asyncio.Event()
    manager = make_manager(tmp_path, analyzer=FlagEveryFile(gate), max_concurrent=1)
    pending = [await submit(manager) for _ in range(5)]

    with pytest.raises(ScanQueueFullError):
        await manager.new_workspace()

    gate.set()
    for scan_id in pending:
        await finish(manager, scan_id)
    assert (await manager.new_workspace()).root.is_dir()
