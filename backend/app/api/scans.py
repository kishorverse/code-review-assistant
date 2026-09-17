"""Scan endpoints: upload, status, live events, findings, files, reports and deletion.

There is deliberately no endpoint that lists scans: a scan id is only known to
whoever submitted the scan, which is what keeps one user's scans private from
another's in this prototype without accounts.
"""

import asyncio
import json
import shutil
from collections import defaultdict
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Header, Query, Request, Response, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, ConfigDict, NonNegativeInt

from app.errors import UploadTooLargeError
from app.events import ScanStatus
from app.findings import Finding, FindingStatus, Severity
from app.ingest.models import SkippedFile
from app.report.document import Report, ReportCounts
from app.report.html import render_html
from app.report.sarif import to_sarif
from app.report.score import QualityScore
from app.review.answers import ReviewSummary
from app.review.planner import Depth, ReviewOptions
from app.scans.event_log import EventLog
from app.scans.manager import ScanInfo, ScanManager

router = APIRouter(prefix="/scans", tags=["scans"])


def get_manager(request: Request) -> ScanManager:
    """The application's scan manager."""
    manager: ScanManager = request.app.state.scans
    return manager


Manager = Annotated[ScanManager, Depends(get_manager)]


class ScanDetail(BaseModel):
    """A scan's status, and its headline results once it has finished."""

    model_config = ConfigDict(frozen=True)

    scan: ScanInfo
    summary: ReportCounts | None = None
    score: QualityScore | None = None
    ai_summary: ReviewSummary | None = None


class FindingDecision(BaseModel):
    """A reviewer's decision on a finding. ``open`` restores a dismissed or rejected finding."""

    status: Literal["open", "accepted", "rejected"]


class FileEntry(BaseModel):
    """One extracted file, with how many reported findings it has."""

    model_config = ConfigDict(frozen=True)

    path: str
    language: str | None
    lines: NonNegativeInt | None
    findings: NonNegativeInt
    highest_severity: Severity | None


class FileTree(BaseModel):
    """The scan's files and the files left out of it."""

    model_config = ConfigDict(frozen=True)

    files: list[FileEntry]
    skipped: list[SkippedFile]


class FileContent(BaseModel):
    """The text of one extracted file."""

    model_config = ConfigDict(frozen=True)

    path: str
    language: str | None
    content: str


class ReportFormat(StrEnum):
    """Download formats."""

    JSON = "json"
    SARIF = "sarif"
    HTML = "html"


_MEDIA_TYPES = {
    ReportFormat.JSON: ("application/json", "json"),
    ReportFormat.SARIF: ("application/sarif+json", "sarif"),
    ReportFormat.HTML: ("text/html; charset=utf-8", "html"),
}


@router.post("", status_code=202)
async def create_scan(
    manager: Manager,
    file: UploadFile,
    depth: Annotated[Depth, Form()] = Depth.STANDARD,
    allow_external: Annotated[bool, Form()] = False,
) -> ScanInfo:
    """Upload a source file or a ``.zip`` and start scanning it.

    Hosted models receive code only when ``allow_external`` is true.
    """
    if file.size is not None and file.size > manager.max_upload_bytes:
        raise UploadTooLargeError("The upload is larger than the limit")
    workspace = await manager.new_workspace()  # Refuses when too many scans are pending.
    try:
        with manager.upload_path(workspace).open("wb") as destination:
            await asyncio.to_thread(shutil.copyfileobj, file.file, destination)
    except BaseException:
        await manager.discard(workspace)
        raise
    options = ReviewOptions(depth=depth, allow_external=allow_external)
    return await manager.submit(workspace, file.filename or "", options)


@router.get("/{scan_id}")
async def get_scan(scan_id: str, manager: Manager) -> ScanDetail:
    """A scan's status, with its counts, score and AI summary once finished."""
    info = await manager.info(scan_id)
    if info.status is not ScanStatus.DONE:
        return ScanDetail(scan=info)
    report = await manager.report(scan_id)
    return ScanDetail(
        scan=info,
        summary=report.summary,
        score=report.score,
        ai_summary=report.review.summary if report.review else None,
    )


async def _event_log(scan_id: str, manager: Manager) -> EventLog:
    # Resolved as a dependency so an unknown scan gets a 404 before streaming starts.
    return await manager.events(scan_id)


@router.get("/{scan_id}/events", response_class=EventSourceResponse)
async def scan_events(
    log: Annotated[EventLog, Depends(_event_log)],
    last_event_id: Annotated[int | None, Header(ge=0)] = None,
) -> AsyncIterator[ServerSentEvent]:
    """The scan's events as server-sent events, replayed after ``Last-Event-ID``, then live."""
    async for stored in log.follow(last_event_id or 0):
        yield ServerSentEvent(
            id=str(stored.id),
            event=stored.event.kind,
            data=stored.event.model_dump(mode="json"),
        )


@router.get("/{scan_id}/findings")
async def list_findings(scan_id: str, manager: Manager) -> list[Finding]:
    """Every finding, including those dismissed, rejected or below the confidence threshold."""
    return (await manager.report(scan_id)).findings


@router.patch("/{scan_id}/findings/{finding_id}")
async def decide_finding(
    scan_id: str, finding_id: str, decision: FindingDecision, manager: Manager
) -> Finding:
    """Accept, reject or restore a finding."""
    return await manager.set_finding_status(scan_id, finding_id, FindingStatus(decision.status))


@router.get("/{scan_id}/files")
async def list_files(scan_id: str, manager: Manager) -> FileTree:
    """The scan's files with reported finding counts, and the files that were skipped."""
    report = await manager.report(scan_id)
    return FileTree(files=file_entries(report), skipped=report.skipped_files)


@router.get("/{scan_id}/files/{path:path}")
async def read_file(scan_id: str, path: str, manager: Manager) -> FileContent:
    """The text of one of the scan's files, for the code viewer."""
    content = await manager.read_file(scan_id, path)
    languages = {file.path: file.language for file in (await manager.report(scan_id)).files}
    return FileContent(path=path, language=languages.get(path), content=content)


@router.get("/{scan_id}/report")
async def download_report(
    scan_id: str,
    manager: Manager,
    report_format: Annotated[ReportFormat, Query(alias="format")] = ReportFormat.JSON,
) -> Response:
    """The report as a JSON, SARIF or HTML file download."""
    report = await manager.report(scan_id)
    if report_format is ReportFormat.JSON:
        body = report.model_dump_json(indent=2)
    elif report_format is ReportFormat.SARIF:
        body = json.dumps(to_sarif(report), indent=2)
    else:
        body = render_html(report)
    media_type, extension = _MEDIA_TYPES[report_format]
    return Response(
        content=body,
        media_type=media_type,
        headers={
            # A download, never rendered in the API's origin.
            "Content-Disposition": f'attachment; filename="margin-report.{extension}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{scan_id}", status_code=204)
async def delete_scan(scan_id: str, manager: Manager) -> None:
    """Stop the scan if it is running and delete the upload and everything derived from it."""
    await manager.delete(scan_id)


def file_entries(report: Report) -> list[FileEntry]:
    """Every scanned file with its reported findings, in path order."""
    reviewed = {file.path: file for file in report.files}
    by_file: dict[str, list[Finding]] = defaultdict(list)
    for finding in report.reported_findings():
        by_file[finding.file_path].append(finding)
    entries = []
    for path in sorted(report.scanned_files):
        findings = by_file.get(path, [])
        file = reviewed.get(path)
        entries.append(
            FileEntry(
                path=path,
                language=file.language if file else None,
                lines=file.lines if file else None,
                findings=len(findings),
                highest_severity=max(
                    (finding.severity for finding in findings),
                    key=lambda severity: severity.rank,
                    default=None,
                ),
            )
        )
    return entries
