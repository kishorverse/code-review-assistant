import pytest
from pydantic import ValidationError

from app.llm.models import LLMRequest, Task


def test_requests_default_to_no_external_providers() -> None:
    request = LLMRequest(task=Task.REVIEW, system="s", user="u")

    assert request.allow_external is False
    assert request.exclude_providers == frozenset()
    assert request.only_providers is None


def test_estimated_tokens_include_prompt_and_output_budget() -> None:
    request = LLMRequest(task=Task.REVIEW, system="a" * 7, user="b" * 7, max_output_tokens=100)

    assert request.estimated_tokens() == 4 + 100


def test_rejects_out_of_range_sampling_settings() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(task=Task.REVIEW, system="s", user="u", temperature=3.0)
    with pytest.raises(ValidationError):
        LLMRequest(task=Task.REVIEW, system="s", user="u", max_output_tokens=0)
