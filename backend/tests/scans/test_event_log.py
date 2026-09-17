import asyncio
from pathlib import Path

from app.events import ScanStage, ScanStatus, StageEvent, StatusEvent
from app.scans.event_log import EventLog


async def collect(log: EventLog, after: int = 0) -> list[int]:
    return [stored.id async for stored in log.follow(after)]


async def test_numbers_events_and_replays_after_an_id(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    for stage in (ScanStage.INGESTING, ScanStage.PREPROCESSING, ScanStage.ANALYZING):
        await log.emit(StageEvent(stage=stage))
    await log.close()

    assert await collect(log) == [1, 2, 3]
    assert await collect(log, after=2) == [3]
    assert await collect(log, after=99) == []


async def test_followers_receive_live_events_until_the_log_closes(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    await log.emit(StageEvent(stage=ScanStage.INGESTING))
    follower = asyncio.create_task(collect(log))
    await asyncio.sleep(0)

    await log.emit(StageEvent(stage=ScanStage.ANALYZING))
    await log.emit(StatusEvent(status=ScanStatus.DONE))
    await log.close()

    assert await asyncio.wait_for(follower, timeout=2) == [1, 2, 3]


async def test_a_closed_log_is_read_back_from_its_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    await log.emit(StageEvent(stage=ScanStage.INGESTING))
    await log.emit(StatusEvent(status=ScanStatus.FAILED, message="Scan failed unexpectedly."))
    await log.close()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")

    loaded = await asyncio.to_thread(EventLog.load, path)

    assert loaded.closed
    events = [stored.event async for stored in loaded.follow()]
    assert events == [
        StageEvent(stage=ScanStage.INGESTING),
        StatusEvent(status=ScanStatus.FAILED, message="Scan failed unexpectedly."),
    ]


async def test_events_after_closing_are_ignored(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "events.jsonl")
    await log.close()

    await log.emit(StageEvent(stage=ScanStage.DONE))

    assert len(log) == 0
    assert not (tmp_path / "events.jsonl").exists()


async def test_concurrent_emitters_keep_file_and_memory_in_the_same_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    stages = list(ScanStage) * 5

    await asyncio.gather(*(log.emit(StageEvent(stage=stage)) for stage in stages))
    await log.close()

    loaded = await asyncio.to_thread(EventLog.load, path)
    assert [s.model_dump() async for s in loaded.follow()] == [
        s.model_dump() async for s in log.follow()
    ]
    assert len(loaded) == len(stages)
