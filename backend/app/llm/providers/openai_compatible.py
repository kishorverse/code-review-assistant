"""Providers with an OpenAI-compatible chat completions API.

Hugging Face Inference Providers, NVIDIA NIM and a local Ollama server all
accept the same request, so one client covers them; only the base URL, the
key and whether data leaves the machine differ.
"""

import httpx
from pydantic import SecretStr

from app.errors import ProviderRequestError
from app.llm.clock import Clock
from app.llm.models import LLMRequest, LLMResponse
from app.llm.providers.base import json_object, post_json, raise_for_status, usage_count


class OpenAICompatibleProvider:
    """A chat completions endpoint."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: SecretStr | None,
        external: bool,
        client: httpx.AsyncClient,
        clock: Clock,
        timeout_seconds: float = 60.0,
        json_mode: bool = True,
    ) -> None:
        self._name = name
        self._model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._external = external
        self._client = client
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._json_mode = json_mode

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
        """See :class:`~app.llm.providers.base.LLMProvider`."""
        return self._external

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send one chat completion request."""
        body: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        if request.json_output and self._json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = (
            {"Authorization": f"Bearer {self._api_key.get_secret_value()}"} if self._api_key else {}
        )

        response, latency_ms = await post_json(
            self._client,
            self._name,
            self._url,
            headers=headers,
            body=body,
            timeout_seconds=self._timeout_seconds,
        )
        raise_for_status(self._name, response, self._clock.now())
        payload = json_object(self._name, response)

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderRequestError(self._name, "response had no message content") from error
        if not isinstance(content, str) or not content.strip():
            raise ProviderRequestError(self._name, "response message was empty")

        usage = payload.get("usage")
        return LLMResponse(
            text=content,
            provider=self._name,
            model=str(payload.get("model") or self._model),
            input_tokens=usage_count(usage, "prompt_tokens"),
            output_tokens=usage_count(usage, "completion_tokens"),
            latency_ms=latency_ms,
        )
