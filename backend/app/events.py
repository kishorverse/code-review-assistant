"""Progress events emitted while a scan runs.

The CLI prints them, and the web API streams them to the browser, so the same
pipeline serves batch and interactive use.
"""

from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from app.findings import Finding
from app.static.base import ToolStatus


class ScanStage(StrEnum):
    """Pipeline stages, in order."""

    INGESTING = "ingesting"
    PREPROCESSING = "preprocessing"
    ANALYZING = "analyzing"
    DONE = "done"


class StageEvent(BaseModel):
    """The scan entered a new stage."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["stage"] = "stage"
    stage: ScanStage


class ToolEvent(BaseModel):
    """An analyzer started or finished."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["tool"] = "tool"
    tool: str
    state: Literal["started"] | ToolStatus
    finding_count: NonNegativeInt = 0
    duration_ms: NonNegativeInt = 0
    message: str | None = None


class FindingEvent(BaseModel):
    """A finding is ready to show."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["finding"] = "finding"
    finding: Finding


ScanEvent = Annotated[StageEvent | ToolEvent | FindingEvent, Field(discriminator="kind")]


class EventSink(Protocol):
    """Receives scan events; implementations must not raise."""

    async def emit(self, event: ScanEvent) -> None:
        """Handle one event."""
        ...


class NullSink:
    """Discards every event."""

    async def emit(self, event: ScanEvent) -> None:
        """Ignore the event."""


class CollectingSink:
    """Keeps every event in order, for tests and batch runs."""

    def __init__(self) -> None:
        self.events: list[ScanEvent] = []

    async def emit(self, event: ScanEvent) -> None:
        """Record the event."""
        self.events.append(event)
