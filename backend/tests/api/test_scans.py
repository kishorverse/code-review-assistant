import asyncio
import io
import json
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft4Validator

from app.config import Settings
from app.events import ScanStatus
from app.main import create_app
from tests.scans.fakes import SOURCE, FlagEveryFile, wait_for_status

SARIF_SCHEMA = Path(__file__).parents[1] / "report" / "fixtures" / "sarif-schema-2.1.0.json"


def make_api(tmp_path: Path, analyzer: FlagEveryFile) -> Any:
    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_mode="mock",
        storage_dir=tmp_path / "storage",
        cors_origins=["http://testserver.local"],
    )
    return create_app(settings, analyzers=lambda: [analyzer])


@pytest.fixture
def gate() -> asyncio.Event:
    released = asyncio.Event()
    released.set()
    return released


@pytest.fixture
async def app(tmp_path: Path, gate: asyncio.Event) -> AsyncIterator[FastAPI]:
    application = make_api(tmp_path, FlagEveryFile(gate))
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def upload(
    client: AsyncClient, content: bytes = SOURCE.encode(), name: str = "stats.py", **form: str
) -> Any:
    return await client.post(
        "/api/scans", files={"file": (name, content)}, data={"depth": "quick", **form}
    )


async def read_events(client: AsyncClient, scan_id: str, **headers: str) -> list[dict[str, Any]]:
    """Read a scan's whole event stream.

    The test transport delivers a response only once it is complete, so this is
    for scans that finish; tests wait for other states through the scan manager.
    """
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    async with client.stream("GET", f"/api/scans/{scan_id}/events", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                current["id"] = int(line[4:])
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
            elif not line and current:
                events.append(current)
                current = {}
    return events


async def test_upload_follow_review_and_download(api: AsyncClient) -> None:
    created = await upload(api)
    assert created.status_code == 202, created.text
    scan = created.json()
    assert (scan["status"], scan["source"], scan["depth"]) == ("queued", "stats.py", "quick")

    events = await asyncio.wait_for(read_events(api, scan["id"]), timeout=10)
    assert [e["id"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1] == {
        "id": len(events),
        "event": "status",
        "data": {"kind": "status", "status": "done", "message": None},
    }
    assert {"stage", "tool", "status", "finding", "llm_call"} <= {e["event"] for e in events}

    detail = (await api.get(f"/api/scans/{scan['id']}")).json()
    assert detail["scan"]["status"] == "done"
    assert detail["summary"]["findings"] == 1
    assert detail["score"]["grade"] in {"A", "B", "C", "D", "E"}
    streamed_calls = [e["data"]["call"] for e in events if e["event"] == "llm_call"]
    assert detail["calls"] == streamed_calls

    findings = (await api.get(f"/api/scans/{scan['id']}/findings")).json()
    assert [f["title"] for f in findings] == ["Possible division by zero"]
    decided = await api.patch(
        f"/api/scans/{scan['id']}/findings/{findings[0]['id']}", json={"status": "rejected"}
    )
    assert decided.json()["status"] == "rejected"
    detail = (await api.get(f"/api/scans/{scan['id']}")).json()
    assert detail["summary"]["not_reported"]["rejected"] == 1

    tree = (await api.get(f"/api/scans/{scan['id']}/files")).json()
    assert tree["files"] == [
        {
            "path": "stats.py",
            "language": "python",
            "lines": 2,
            "findings": 0,
            "highest_severity": None,
        }
    ]
    file = (await api.get(f"/api/scans/{scan['id']}/files/stats.py")).json()
    assert (file["content"], file["language"]) == (SOURCE, "python")

    for report_format, media_type in (
        ("json", "application/json"),
        ("sarif", "application/sarif+json"),
        ("html", "text/html; charset=utf-8"),
    ):
        response = await api.get(
            f"/api/scans/{scan['id']}/report", params={"format": report_format}
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == media_type
        assert response.headers["content-disposition"] == (
            f'attachment; filename="margin-report.{report_format}"'
        )
        assert response.headers["x-content-type-options"] == "nosniff"
    sarif = (await api.get(f"/api/scans/{scan['id']}/report", params={"format": "sarif"})).json()
    schema = json.loads(SARIF_SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft4Validator(schema).iter_errors(sarif)) == []

    assert (await api.delete(f"/api/scans/{scan['id']}")).status_code == 204
    assert (await api.get(f"/api/scans/{scan['id']}")).status_code == 404


async def test_events_resume_after_the_last_event_id(api: AsyncClient) -> None:
    scan_id = (await upload(api)).json()["id"]
    everything = await asyncio.wait_for(read_events(api, scan_id), timeout=10)

    resumed = await read_events(api, scan_id, **{"Last-Event-ID": "3"})

    assert resumed == everything[3:]


async def test_rejected_archives_get_the_reason(api: AsyncClient, tmp_path: Path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.py", "x = 1\n")

    response = await upload(api, archive.getvalue(), "evil.zip")

    assert response.status_code == 400
    assert response.json()["reason"] == "path_traversal"
    assert list((tmp_path / "storage").iterdir()) == []


async def test_oversized_and_unsized_uploads_are_refused_before_reading(api: AsyncClient) -> None:
    oversized = await api.post(
        "/api/scans", content=b"x", headers={"Content-Length": str(50 * 1024 * 1024)}
    )

    async def chunks() -> AsyncIterator[bytes]:
        yield b"--boundary\r\n"

    unsized = await api.post("/api/scans", content=chunks())

    assert oversized.status_code == 413
    assert unsized.status_code == 411


@pytest.mark.parametrize(
    "path",
    [
        "/api/scans/00000000000000000000000000000000",
        "/api/scans/not-a-scan-id",
        "/api/scans/00000000000000000000000000000000/events",
        "/api/scans/00000000000000000000000000000000/report",
        "/api/scans/00000000000000000000000000000000/files/app.py",
    ],
)
async def test_unknown_scans_are_not_found(api: AsyncClient, path: str) -> None:
    response = await api.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Scan not found"}


async def test_only_the_scans_own_files_are_served(api: AsyncClient) -> None:
    scan_id = (await upload(api)).json()["id"]
    await asyncio.wait_for(read_events(api, scan_id), timeout=10)

    for path in ("..%2F..%2Fresults%2Fscan.json", "results/scan.json", "other.py"):
        response = await api.get(f"/api/scans/{scan_id}/files/{path}")
        assert response.status_code == 404, path


async def test_results_are_not_available_while_the_scan_runs(
    api: AsyncClient, app: FastAPI, gate: asyncio.Event
) -> None:
    gate.clear()
    scan_id = (await upload(api)).json()["id"]
    await wait_for_status(app.state.scans, scan_id, ScanStatus.RUNNING)

    detail = (await api.get(f"/api/scans/{scan_id}")).json()
    report = await api.get(f"/api/scans/{scan_id}/report")
    decision = await api.patch(f"/api/scans/{scan_id}/findings/{'a' * 32}", json={"status": "open"})

    assert detail["scan"]["status"] == "running"
    assert detail["summary"] is None
    assert (report.status_code, decision.status_code) == (409, 409)
    gate.set()


async def test_reviewers_cannot_set_ai_statuses(api: AsyncClient) -> None:
    scan_id = (await upload(api)).json()["id"]
    await asyncio.wait_for(read_events(api, scan_id), timeout=10)
    finding_id = (await api.get(f"/api/scans/{scan_id}/findings")).json()[0]["id"]

    response = await api.patch(
        f"/api/scans/{scan_id}/findings/{finding_id}", json={"status": "dismissed_by_ai"}
    )

    assert response.status_code == 422


async def test_providers_lists_the_enabled_models(api: AsyncClient) -> None:
    body = (await api.get("/api/providers")).json()

    assert body["mode"] == "mock"
    names = {provider["name"]: provider for provider in body["providers"]}
    assert set(names) == {"gemini", "nvidia", "hf-large", "hf-small", "local"}
    assert names["local"]["external"] is False
    assert names["gemini"]["state"] == "closed"


async def test_uploads_are_refused_with_retry_after_when_the_queue_is_full(
    api: AsyncClient, gate: asyncio.Event
) -> None:
    gate.clear()
    statuses = [(await upload(api)).status_code for _ in range(11)]

    refused = await upload(api)

    assert statuses == [202] * 10 + [503]
    assert refused.status_code == 503
    assert refused.headers["retry-after"] == "30"
    gate.set()
