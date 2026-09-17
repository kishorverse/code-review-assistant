"""A scan's events, numbered, kept in memory and appended to a file.

Numbering lets a browser that lost its connection resume with the
``Last-Event-ID`` header, and the file lets a finished scan's progress be
replayed after the server restarts. Followers wait for new events and stop once
the log is closed, which happens when the scan finishes.
"""

import asyncio
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path

from pydantic import BaseModel, ConfigDict, PositiveInt, ValidationError

from app.events import ScanEvent


class StoredEvent(BaseModel):
    """An event with its position in the log, starting at 1."""

    model_config = ConfigDict(frozen=True)

    id: PositiveInt
    event: ScanEvent


class EventLog:
    """An :class:`~app.events.EventSink` that records events for replay."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: list[StoredEvent] = []
        self._closed = False
        self._changed = asyncio.Condition()
        self._write_lock = asyncio.Lock()

    @classmethod
    def load(cls, path: Path) -> "EventLog":
        """A closed log read back from its file. Unreadable lines are skipped.

        This is blocking I/O; call it with ``asyncio.to_thread`` from async code.
        """
        log = cls(path)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    log._events.append(StoredEvent.model_validate_json(line))
                except ValidationError:
                    continue
        log._closed = True
        return log

    @property
    def closed(self) -> bool:
        """Whether the log will receive no more events."""
        return self._closed

    def __len__(self) -> int:
        return len(self._events)

    async def emit(self, event: ScanEvent) -> None:
        """Append an event, persist it and wake followers. Events after closing are ignored."""
        async with self._write_lock:
            if self._closed:
                return
            stored = StoredEvent(id=len(self._events) + 1, event=event)
            await asyncio.to_thread(_append_line, self._path, stored.model_dump_json())
            self._events.append(stored)
        async with self._changed:
            self._changed.notify_all()

    async def close(self) -> None:
        """Mark the log finished and release every follower."""
        async with self._write_lock:
            self._closed = True
        async with self._changed:
            self._changed.notify_all()

    async def follow(self, after: int = 0) -> AsyncIterator[StoredEvent]:
        """Yield events with ids greater than ``after``, waiting for new ones until closed."""
        position = max(0, after)
        while True:
            while position < len(self._events):
                yield self._events[position]
                position += 1
            if self._closed:
                return
            async with self._changed:
                await self._changed.wait_for(partial(self._has_more_than, position))

    def _has_more_than(self, position: int) -> bool:
        return self._closed or len(self._events) > position


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
