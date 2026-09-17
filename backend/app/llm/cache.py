"""In-memory response cache, so reviewing unchanged code again costs no API calls.

Entries are keyed by everything that shapes a model's answer: the task, both
prompts and the generation parameters. The provider is not part of the key; the
router decides whether a cached answer's provider is acceptable for a request.
"""

import hashlib
import json
from collections import OrderedDict

from app.llm.models import LLMRequest, LLMResponse

DEFAULT_MAX_ENTRIES = 512


def cache_key(request: LLMRequest) -> str:
    """A stable digest of the request fields that affect the response."""
    material = json.dumps(
        [
            request.task,
            request.system,
            request.user,
            request.json_output,
            request.temperature,
            request.max_output_tokens,
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()


class ResponseCache:
    """A least-recently-used cache of successful responses."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, LLMResponse] = OrderedDict()

    def get(self, request: LLMRequest) -> LLMResponse | None:
        """The cached response for an identical request, marked as cached."""
        key = cache_key(request)
        response = self._entries.get(key)
        if response is None:
            return None
        self._entries.move_to_end(key)
        return response.model_copy(update={"cached": True, "latency_ms": 0})

    def put(self, request: LLMRequest, response: LLMResponse) -> None:
        """Store a response, evicting the least recently used entry when full."""
        if self._max_entries <= 0:
            return
        key = cache_key(request)
        self._entries[key] = response
        self._entries.move_to_end(key)
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
