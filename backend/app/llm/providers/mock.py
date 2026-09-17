"""A deterministic in-process provider for tests, CI and offline demos (``LLM_MODE=mock``)."""

import json
from collections.abc import Callable

from app.llm.models import LLMRequest, LLMResponse, Task

Responder = Callable[[LLMRequest], str]

_DEFAULT_RESPONSES: dict[Task, dict[str, object]] = {
    Task.REVIEW: {"static_judgements": [], "findings": []},
    Task.STYLE: {"static_judgements": [], "findings": []},
    Task.VERIFY: {
        "verdict": "uncertain",
        "reason": "Mock provider: no verification was performed.",
        "corrected_severity": None,
        "confidence": 0.5,
    },
    Task.SUMMARIZE: {
        "headline": "Mock summary: no model was called.",
        "strengths": [],
        "top_risks": [],
        "recommended_next_steps": [],
    },
}


def default_response(request: LLMRequest) -> str:
    """A valid, empty-handed JSON answer for each task."""
    return json.dumps(_DEFAULT_RESPONSES[request.task])


class MockProvider:
    """Answers every request locally with a responder function."""

    def __init__(
        self,
        name: str = "mock",
        model: str = "mock-model",
        respond: Responder = default_response,
        external: bool = False,
    ) -> None:
        self._name = name
        self._model = model
        self._respond = respond
        self._external = external

    @property
    def name(self) -> str:
        """See :class:`~app.llm.providers.base.LLMProvider`."""
        return self._name

    @property
    def model(self) -> str:
        """See :class:`~app.llm.providers.base.LLMProvider`."""
        return self._model

    @property
    def external(self) -> bool:
        """Mocks stand in for external providers in tests, so this is configurable."""
        return self._external

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the responder's text with estimated token counts."""
        text = self._respond(request)
        return LLMResponse(
            text=text,
            provider=self._name,
            model=self._model,
            input_tokens=request.estimated_tokens() - request.max_output_tokens,
            output_tokens=max(1, len(text) // 4),
        )
