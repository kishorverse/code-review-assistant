from app.llm.cache import ResponseCache, cache_key
from app.llm.models import LLMRequest, LLMResponse, Task

REQUEST = LLMRequest(task=Task.REVIEW, system="system", user="1 | x = 1")


def response(text: str = "{}") -> LLMResponse:
    return LLMResponse(text=text, provider="nvidia", model="m", latency_ms=900)


def test_returns_a_cached_copy_for_an_identical_request() -> None:
    cache = ResponseCache()
    cache.put(REQUEST, response())

    hit = cache.get(REQUEST.model_copy())

    assert hit is not None
    assert (hit.text, hit.provider, hit.cached, hit.latency_ms) == ("{}", "nvidia", True, 0)


def test_anything_that_shapes_the_answer_changes_the_key() -> None:
    variants = [
        REQUEST.model_copy(update={"task": Task.STYLE}),
        REQUEST.model_copy(update={"system": "other"}),
        REQUEST.model_copy(update={"user": "1 | x = 2"}),
        REQUEST.model_copy(update={"json_output": False}),
        REQUEST.model_copy(update={"temperature": 0.7}),
        REQUEST.model_copy(update={"max_output_tokens": 100}),
    ]

    keys = {cache_key(variant) for variant in variants}

    assert len(keys) == len(variants)
    assert cache_key(REQUEST) not in keys


def test_routing_options_do_not_change_the_key() -> None:
    routed = REQUEST.model_copy(
        update={"allow_external": True, "exclude_providers": frozenset({"gemini"})}
    )

    assert cache_key(routed) == cache_key(REQUEST)


def test_prompt_boundaries_cannot_collide() -> None:
    first = LLMRequest(task=Task.REVIEW, system="ab", user="c")
    second = LLMRequest(task=Task.REVIEW, system="a", user="bc")

    assert cache_key(first) != cache_key(second)


def test_evicts_the_least_recently_used_entry() -> None:
    cache = ResponseCache(max_entries=2)
    requests = [REQUEST.model_copy(update={"user": str(index)}) for index in range(3)]
    cache.put(requests[0], response("0"))
    cache.put(requests[1], response("1"))
    assert cache.get(requests[0]) is not None

    cache.put(requests[2], response("2"))

    assert len(cache) == 2
    assert cache.get(requests[1]) is None
    assert cache.get(requests[0]) is not None


def test_zero_entries_disables_caching() -> None:
    cache = ResponseCache(max_entries=0)
    cache.put(REQUEST, response())

    assert cache.get(REQUEST) is None
