import json

import pytest

from app.llm.models import LLMRequest, Task
from app.llm.providers.mock import MockProvider


@pytest.mark.parametrize("task", list(Task))
async def test_default_responses_are_valid_json_for_every_task(task: Task) -> None:
    response = await MockProvider().complete(LLMRequest(task=task, system="s", user="u"))

    assert isinstance(json.loads(response.text), dict)
    assert response.provider == "mock"


async def test_custom_responder_and_external_flag() -> None:
    provider = MockProvider(
        name="nvidia", respond=lambda request: request.user.upper(), external=True
    )

    response = await provider.complete(LLMRequest(task=Task.REVIEW, system="s", user="hello"))

    assert (response.text, response.provider, provider.external) == ("HELLO", "nvidia", True)
