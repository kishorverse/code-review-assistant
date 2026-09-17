"""Progress events emitted while a scan runs.

The CLI prints them, and the web API streams them to the browser, so the same
pipeline serves batch and interactive use.
"""

from enum import StrEnum
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from app.findings import Finding
from app.llm.models import CallRecord
from app.static.base import ToolStatus


class ScanStatus(StrEnum):
    """Where a scan is in its life."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ScanStage(StrEnum):
    """Pipeline stages, in order."""

    INGESTING = "ingesting"
    PREPROCESSING = "preprocessing"
    ANALYZING = "analyzing"
    REVIEWING = "reviewing"
    VERIFYING = "verifying"
    SUMMARIZING = "summarizing"
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
    """A finding is ready to show. A later event with the same id replaces it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["finding"] = "finding"
    finding: Finding


class ReviewPlanEvent(BaseModel):
    """What LLM review is about to do."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["review_plan"] = "review_plan"
    review_chunks: NonNegativeInt
    style_chunks: NonNegativeInt
    skipped_chunks: NonNegativeInt


class CallEvent(BaseModel):
    """A model call attempt finished, successfully or not."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["llm_call"] = "llm_call"
    call: CallRecord


class StatusEvent(BaseModel):
    """The scan's status changed. ``done`` and ``failed`` are the last event of a scan."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["status"] = "status"
    status: ScanStatus
    message: str | None = None


ScanEvent = Annotated[
    StageEvent | ToolEvent | FindingEvent | ReviewPlanEvent | CallEvent | StatusEvent,
    Field(discriminator="kind"),
]


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
