"""Run scans submitted through the web API.

A submission is checked while the request is still open: the upload is
extracted into a fresh workspace, so a rejected archive gets an immediate,
specific error. The rest of the scan runs in the background, a few at a time.
Each scan records its status, events and finally its report in its workspace,
so it can be found again after a restart, and is deleted with the workspace
when the user deletes it or its retention period ends.
"""

import asyncio
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path, PurePosixPath

import structlog
from pydantic import BaseModel, ConfigDict

from app.errors import (
    FileNotInScanError,
    InvalidScanIdError,
    ScanNotFinishedError,
    ScanNotFoundError,
    ScanQueueFullError,
)
from app.events import ScanStatus, StatusEvent
from app.findings import Finding, FindingStatus
from app.ingest.models import IngestResult
from app.ingest.storage import ScanStorage, ScanWorkspace, new_scan_id
from app.ingest.upload import ingest_upload
from app.llm.router import Router
from app.pipeline import ReviewSetup, ScanSettings, run_scan
from app.report.document import Report, build_report, set_finding_status
from app.review.planner import Depth, ReviewOptions
from app.scans.event_log import EventLog
from app.static.base import Analyzer

INFO_FILE = "scan.json"
EVENTS_FILE = "events.jsonl"
REPORT_FILE = "report.json"
MAX_SOURCE_NAME = 120
FAILED_MESSAGE = "The scan failed unexpectedly."
INTERRUPTED_MESSAGE = "The scan was interrupted by a server restart."
UPLOAD_NAME = "upload"
PENDING_PER_RUNNING = 5
"""How many scans may be pending (queued or running) for each scan allowed to run at once."""

AnalyzerFactory = Callable[[], list[Analyzer]]
Clock = Callable[[], datetime]

log = structlog.get_logger(__name__)


class ScanInfo(BaseModel):
    """A scan's status and settings, as clients see them."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    status: ScanStatus
    depth: Depth
    allow_external: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


@dataclass
class _Scan:
    info: ScanInfo
    workspace: ScanWorkspace
    log: EventLog
    report: Report | None = None
    task: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScanManager:
    """Creates, runs, finds and removes API scans."""

    def __init__(
        self,
        storage: ScanStorage,
        *,
        router: Router,
        analyzers: AnalyzerFactory,
        retention: timedelta,
        max_concurrent: int,
        scan_settings: ScanSettings | None = None,
        now: Clock = _utc_now,
    ) -> None:
        self._storage = storage
        self._router = router
        self._analyzers = analyzers
        self._retention = retention
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_pending = max_concurrent * PENDING_PER_RUNNING
        self._settings = scan_settings or ScanSettings()
        self._now = now
        self._scans: dict[str, _Scan] = {}
        self._loading = asyncio.Lock()

    @property
    def max_upload_bytes(self) -> int:
        """The largest upload accepted."""
        return self._settings.limits.max_archive_bytes

    async def new_workspace(self) -> ScanWorkspace:
        """Create an empty workspace to receive an upload into ``upload_path``.

        Raises:
            ScanQueueFullError: If too many scans are pending, so an upload flood
                cannot fill the disk.
        """
        pending = sum(
            scan.info.status in (ScanStatus.QUEUED, ScanStatus.RUNNING)
            for scan in self._scans.values()
        )
        if pending >= self._max_pending:
            raise ScanQueueFullError("Too many scans are in progress; try again shortly")
        return await asyncio.to_thread(self._storage.create, new_scan_id())

    @staticmethod
    def upload_path(workspace: ScanWorkspace) -> Path:
        """Where the API writes the uploaded bytes."""
        return workspace.upload_dir / UPLOAD_NAME

    async def discard(self, workspace: ScanWorkspace) -> None:
        """Delete a workspace whose upload was not submitted."""
        await asyncio.to_thread(self._storage.delete, workspace.scan_id)

    async def submit(
        self, workspace: ScanWorkspace, filename: str, options: ReviewOptions
    ) -> ScanInfo:
        """Extract the upload and start the scan in the background.

        Raises:
            IngestError: If the upload is rejected; the workspace is deleted.
        """
        try:
            ingested = await asyncio.to_thread(
                ingest_upload,
                self.upload_path(workspace),
                filename,
                workspace.source_dir,
                self._settings.limits,
            )
        except BaseException:
            await self.discard(workspace)
            raise
        info = ScanInfo(
            id=workspace.scan_id,
            source=display_name(filename),
            status=ScanStatus.QUEUED,
            depth=options.depth,
            allow_external=options.allow_external,
            created_at=self._now(),
        )
        scan = _Scan(info, workspace, EventLog(workspace.results_dir / EVENTS_FILE))
        self._scans[info.id] = scan
        await self._set_status(scan, ScanStatus.QUEUED)
        scan.task = asyncio.create_task(self._run(scan, ingested, options))
        return info

    async def info(self, scan_id: str) -> ScanInfo:
        """A scan's status.

        Raises:
            ScanNotFoundError: If there is no such scan.
        """
        return (await self._find(scan_id)).info

    async def events(self, scan_id: str) -> EventLog:
        """A scan's event log, live while it runs.

        Raises:
            ScanNotFoundError: If there is no such scan.
        """
        return (await self._find(scan_id)).log

    async def report(self, scan_id: str) -> Report:
        """A finished scan's report.

        Raises:
            ScanNotFoundError: If there is no such scan.
            ScanNotFinishedError: If the scan has no report yet, or failed.
        """
        return _require_report(await self._find(scan_id))

    async def set_finding_status(
        self, scan_id: str, finding_id: str, status: FindingStatus
    ) -> Finding:
        """Record a reviewer's decision and save the updated report.

        Raises:
            ScanNotFoundError: If there is no such scan.
            ScanNotFinishedError: If the scan has no report yet.
            UnknownFindingError: If the report has no such finding.
        """
        scan = await self._find(scan_id)
        async with scan.lock:
            updated = set_finding_status(_require_report(scan), finding_id, status)
            await asyncio.to_thread(
                _write_atomic, scan.workspace.results_dir / REPORT_FILE, updated.model_dump_json()
            )
            scan.report = updated
        return next(finding for finding in updated.findings if finding.id == finding_id)

    async def read_file(self, scan_id: str, path: str) -> str:
        """The text of one of a finished scan's extracted files.

        Raises:
            ScanNotFoundError: If there is no such scan.
            ScanNotFinishedError: If the scan has no report yet.
            FileNotInScanError: If ``path`` is not one of the scan's files.
        """
        scan = await self._find(scan_id)
        if path not in _require_report(scan).scanned_files:
            raise FileNotInScanError(f"No file {path[:200]!r} in this scan")
        # The path came from ingestion, which only produces safe relative paths.
        full_path = scan.workspace.source_dir.joinpath(*PurePosixPath(path).parts)
        raw = await asyncio.to_thread(full_path.read_bytes)
        return raw.decode("utf-8-sig", errors="replace")

    async def delete(self, scan_id: str) -> None:
        """Stop a scan if it is running and delete everything it stored.

        Raises:
            ScanNotFoundError: If there is no such scan.
        """
        scan = await self._find(scan_id)
        self._scans.pop(scan_id, None)
        await _cancel(scan)
        await scan.log.close()
        await asyncio.to_thread(self._storage.delete, scan_id)
        log.info("scan_deleted", scan_id=scan_id)

    async def purge_expired(self) -> list[str]:
        """Delete scans older than the retention period."""
        removed = await asyncio.to_thread(self._storage.purge_expired, self._retention, self._now())
        for scan_id in removed:
            scan = self._scans.pop(scan_id, None)
            if scan is not None:
                await _cancel(scan)
                await scan.log.close()
        if removed:
            log.info("scans_purged", count=len(removed))
        return removed

    async def close(self) -> None:
        """Stop running scans, for shutdown."""
        for scan in list(self._scans.values()):
            await _cancel(scan)

    async def _run(self, scan: _Scan, ingested: IngestResult, options: ReviewOptions) -> None:
        try:
            async with self._semaphore:
                await self._set_status(scan, ScanStatus.RUNNING, started_at=self._now())
                result = await run_scan(
                    partial(_already_ingested, ingested),
                    scan.workspace,
                    scan.log,
                    settings=self._settings,
                    analyzers=self._analyzers(),
                    review=(
                        None
                        if options.depth is Depth.STATIC
                        else ReviewSetup(self._router, options)
                    ),
                )
                report = build_report(
                    result,
                    source=scan.info.source,
                    min_confidence=options.min_confidence,
                    generated_at=self._now(),
                )
                await asyncio.to_thread(
                    _write_atomic,
                    scan.workspace.results_dir / REPORT_FILE,
                    report.model_dump_json(),
                )
                scan.report = report
                await self._set_status(scan, ScanStatus.DONE, finished_at=self._now())
        except asyncio.CancelledError:
            raise
        except Exception:
            # Boundary: one scan's unexpected failure must not affect the server or other scans.
            log.exception("scan_failed", scan_id=scan.info.id)
            await self._set_status(
                scan, ScanStatus.FAILED, finished_at=self._now(), error=FAILED_MESSAGE
            )
        finally:
            await scan.log.close()

    async def _set_status(self, scan: _Scan, status: ScanStatus, **changes: object) -> None:
        scan.info = scan.info.model_copy(update={"status": status, **changes})
        await asyncio.to_thread(
            _write_atomic, scan.workspace.results_dir / INFO_FILE, scan.info.model_dump_json()
        )
        await scan.log.emit(StatusEvent(status=status, message=scan.info.error))

    async def _find(self, scan_id: str) -> _Scan:
        scan = self._scans.get(scan_id)
        if scan is not None:
            return scan
        async with self._loading:
            scan = self._scans.get(scan_id)
            if scan is None:
                scan = await self._load(scan_id)
                self._scans[scan_id] = scan
        return scan

    async def _load(self, scan_id: str) -> _Scan:
        try:
            workspace = self._storage.workspace(scan_id)
        except InvalidScanIdError as error:
            raise ScanNotFoundError("Scan not found") from error
        results = workspace.results_dir
        info_text = await asyncio.to_thread(_read_optional, results / INFO_FILE)
        if info_text is None:
            raise ScanNotFoundError("Scan not found")
        info = ScanInfo.model_validate_json(info_text)
        event_log = await asyncio.to_thread(EventLog.load, results / EVENTS_FILE)
        scan = _Scan(info, workspace, event_log)
        report_text = await asyncio.to_thread(_read_optional, results / REPORT_FILE)
        if report_text is not None:
            scan.report = Report.model_validate_json(report_text)
        if info.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
            scan.info = info.model_copy(
                update={"status": ScanStatus.FAILED, "error": INTERRUPTED_MESSAGE}
            )
            await asyncio.to_thread(_write_atomic, results / INFO_FILE, scan.info.model_dump_json())
        return scan


def display_name(filename: str) -> str:
    """A safe, short name for what was uploaded: the last path component, printable only."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    printable = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip()
    return printable[:MAX_SOURCE_NAME] or UPLOAD_NAME


def _already_ingested(ingested: IngestResult, _source_dir: Path) -> IngestResult:
    return ingested


def _require_report(scan: _Scan) -> Report:
    if scan.report is None:
        raise ScanNotFinishedError(f"The scan is {scan.info.status.value} and has no report")
    return scan.report


async def _cancel(scan: _Scan) -> None:
    task = scan.task
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
