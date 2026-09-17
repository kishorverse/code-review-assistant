"""List the model ids each configured LLM provider key can use.

Model availability changes often, so model ids are never hard-coded. Run this
from ``backend/`` after adding keys to ``.env``, then copy the ids you choose
into ``.env``. Models on a running local server, such as Ollama, are listed too::

    uv run python scripts/list_models.py
    uv run python scripts/list_models.py --match llama
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from pydantic import SecretStr

from app.config import Settings, get_settings

REQUEST_TIMEOUT = httpx.Timeout(20.0)

Fetcher = Callable[[httpx.AsyncClient, str, str], Awaitable[list[str]]]


@dataclass(frozen=True)
class ProviderSource:
    """Where and how to list one provider's models."""

    name: str
    env_var: str
    key: SecretStr | None
    base_url: str
    fetch: Fetcher
    requires_key: bool = True


@dataclass(frozen=True)
class ProviderModels:
    """Outcome of listing one provider's models."""

    provider: str
    models: list[str]
    note: str | None = None


async def fetch_gemini_models(client: httpx.AsyncClient, base_url: str, api_key: str) -> list[str]:
    """Return Gemini models that support text generation, without the ``models/`` prefix."""
    response = await client.get(
        f"{base_url}/models",
        headers={"x-goog-api-key": api_key},
        params={"pageSize": 1000},
    )
    response.raise_for_status()
    return sorted(
        model["name"].removeprefix("models/")
        for model in response.json().get("models", [])
        if "generateContent" in model.get("supportedGenerationMethods", [])
    )


async def fetch_openai_compatible_models(
    client: httpx.AsyncClient, base_url: str, token: str
) -> list[str]:
    """Return model ids from an OpenAI-compatible ``/models`` endpoint.

    Local servers need no token, so an empty token sends no ``Authorization`` header.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.get(f"{base_url}/models", headers=headers)
    response.raise_for_status()
    return sorted(model["id"] for model in response.json().get("data", []))


def provider_sources(settings: Settings) -> list[ProviderSource]:
    """The providers Margin can use, in display order."""
    return [
        ProviderSource(
            "gemini",
            "GEMINI_API_KEY",
            settings.gemini_api_key,
            settings.gemini_base_url,
            fetch_gemini_models,
        ),
        ProviderSource(
            "huggingface",
            "HF_TOKEN",
            settings.hf_token,
            settings.hf_base_url,
            fetch_openai_compatible_models,
        ),
        ProviderSource(
            "nvidia",
            "NVIDIA_API_KEY",
            settings.nvidia_api_key,
            settings.nvidia_base_url,
            fetch_openai_compatible_models,
        ),
        ProviderSource(
            "local",
            "LOCAL_BASE_URL",
            None,
            settings.local_base_url,
            fetch_openai_compatible_models,
            requires_key=False,
        ),
    ]


async def list_provider_models(source: ProviderSource, client: httpx.AsyncClient) -> ProviderModels:
    """List one provider's models, turning expected failures into a readable note."""
    if source.requires_key and source.key is None:
        return ProviderModels(source.name, [], f"not configured (set {source.env_var})")
    key = source.key.get_secret_value() if source.key else ""
    try:
        models = await source.fetch(client, source.base_url, key)
    except httpx.ConnectError:
        if source.requires_key:
            return ProviderModels(source.name, [], "request failed: ConnectError")
        return ProviderModels(
            source.name, [], f"no server at {source.base_url} (start one or set {source.env_var})"
        )
    except httpx.HTTPStatusError as error:
        return ProviderModels(source.name, [], f"request failed: HTTP {error.response.status_code}")
    except httpx.HTTPError as error:
        return ProviderModels(source.name, [], f"request failed: {type(error).__name__}")
    except (KeyError, TypeError, ValueError):
        return ProviderModels(source.name, [], "unexpected response format")
    return ProviderModels(source.name, models)


async def collect_models(settings: Settings, client: httpx.AsyncClient) -> list[ProviderModels]:
    """Query every provider concurrently, keeping display order."""
    return list(
        await asyncio.gather(
            *(list_provider_models(source, client) for source in provider_sources(settings))
        )
    )


def render(results: list[ProviderModels], match: str | None) -> str:
    """Format results for the terminal, optionally filtering ids by substring."""
    lines: list[str] = []
    for result in results:
        if result.note:
            lines.append(f"{result.provider}: {result.note}")
            continue
        models = [m for m in result.models if not match or match.lower() in m.lower()]
        noun = "model" if len(models) == 1 else "models"
        lines.append(f"{result.provider} ({len(models)} {noun})")
        lines.extend(f"  {model}" for model in models)
    return "\n".join(lines)


async def _run(match: str | None) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        results = await collect_models(get_settings(), client)
    print(render(results, match))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List the model ids each configured LLM provider key can use."
    )
    parser.add_argument("--match", help="only show model ids containing this text")
    args = parser.parse_args()
    asyncio.run(_run(args.match))


if __name__ == "__main__":
    main()
