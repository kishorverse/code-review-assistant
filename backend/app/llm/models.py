"""Requests, responses and call records exchanged with LLM providers."""

import math
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

CHARACTERS_PER_TOKEN = 3.5
"""Rough ratio for estimating tokens before a call; exact counts come back in responses."""


class Task(StrEnum):
    """Kinds of LLM work, each routed to the providers best suited to it."""

    REVIEW = "review"
    STYLE = "style"
    VERIFY = "verify"
    SUMMARIZE = "summarize"


class Priority(IntEnum):
    """How long a request may wait for rate-limit capacity before trying another provider."""

    INTERACTIVE = 0
    BATCH = 1


class LLMRequest(BaseModel):
    """One prompt for one task.

    Attributes:
        task: What the call is for; decides provider preference.
        system: System prompt.
        user: User prompt, including any code excerpt.
        json_output: Ask the provider for a JSON object when it supports that.
        max_output_tokens: Upper bound on the response length.
        temperature: Sampling temperature; low values keep reviews consistent.
        priority: Interactive requests wait less for rate-limit capacity.
        allow_external: Whether code may be sent to providers outside this machine.
            Defaults to ``False`` so consent must be given explicitly.
        exclude_providers: Providers that must not handle the request, for example
            the one that produced a finding being verified.
        only_providers: Restrict the request to these providers, for example to
            compare models during evaluation.
    """

    model_config = ConfigDict(frozen=True)

    task: Task
    system: str
    user: str
    json_output: bool = True
    max_output_tokens: PositiveInt = 2048
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    priority: Priority = Priority.BATCH
    allow_external: bool = False
    exclude_providers: frozenset[str] = frozenset()
    only_providers: frozenset[str] | None = None

    def estimated_tokens(self) -> int:
        """Input estimate plus the output budget, used to reserve rate-limit capacity."""
        characters = len(self.system) + len(self.user)
        return math.ceil(characters / CHARACTERS_PER_TOKEN) + self.max_output_tokens


class LLMResponse(BaseModel):
    """A completed call."""

    model_config = ConfigDict(frozen=True)

    text: str
    provider: str
    model: str
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    latency_ms: NonNegativeInt = 0
    cached: bool = False


class CallStatus(StrEnum):
    """Outcome of one attempt to use a provider."""

    OK = "ok"
    CACHED = "cached"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class CallRecord(BaseModel):
    """One attempt, for provenance in reports and the routing evaluation.

    Records never contain prompts or responses, so they can be logged and stored.
    """

    model_config = ConfigDict(frozen=True)

    task: Task
    provider: str
    model: str
    status: CallStatus
    latency_ms: NonNegativeInt = 0
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    detail: str | None = None
