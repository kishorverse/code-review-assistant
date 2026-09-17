"""Builds the router from settings and ``providers.yaml``."""

import asyncio
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.llm.breaker import CircuitBreaker
from app.llm.cache import ResponseCache
from app.llm.clock import Clock, SystemClock
from app.llm.config import ProvidersConfig, load_providers_config
from app.llm.limits import RateLimiter, RateLimits
from app.llm.models import Priority
from app.llm.providers.base import LLMProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from app.llm.router import RoutedProvider, Router


@dataclass(frozen=True)
class _Endpoint:
    name: str
    base_url: str
    key: SecretStr | None
    model: str | None
    external: bool


def build_router(
    settings: Settings, client: httpx.AsyncClient, clock: Clock | None = None
) -> Router:
    """A router over every enabled provider.

    Raises:
        ConfigError: If ``providers.yaml`` is missing or invalid.
    """
    clock = clock or SystemClock()
    config = load_providers_config(settings.providers_config_path)
    return Router(
        build_routed_providers(settings, config, client, clock),
        config.routing,
        clock=clock,
        cache=ResponseCache(config.router.cache_entries),
        max_wait_seconds={priority: config.router.max_wait(priority) for priority in Priority},
    )


def build_routed_providers(
    settings: Settings, config: ProvidersConfig, client: httpx.AsyncClient, clock: Clock
) -> list[RoutedProvider]:
    """Enabled providers with their limiters, breakers and concurrency limits.

    Providers that name the same limits share one limiter, because they draw on
    one account's budget. Mock mode applies no rate limits, so tests and demos
    never wait.
    """
    mock = settings.llm_mode == "mock"
    limiters = {
        group: RateLimiter(
            RateLimits() if mock else limits.to_rate_limits(config.router.safety), clock
        )
        for group, limits in config.limits.items()
    }
    providers = (
        mock_providers(settings) if mock else live_providers(settings, config, client, clock)
    )
    return [
        RoutedProvider(
            provider=provider,
            limiter=limiters[tuning.limits],
            breaker=CircuitBreaker(clock, probe_timeout_seconds=tuning.timeout_seconds),
            semaphore=asyncio.Semaphore(tuning.max_concurrency),
            timeout_seconds=tuning.timeout_seconds,
        )
        for provider in providers
        if (tuning := config.providers.get(provider.name)) is not None
    ]


def live_providers(
    settings: Settings, config: ProvidersConfig, client: httpx.AsyncClient, clock: Clock
) -> list[LLMProvider]:
    """Providers whose model id, and key where one is needed, are configured."""
    providers: list[LLMProvider] = []
    gemini = config.providers.get("gemini")
    if gemini and settings.gemini_api_key and settings.gemini_model:
        providers.append(
            GeminiProvider(
                model=settings.gemini_model,
                base_url=settings.gemini_base_url,
                api_key=settings.gemini_api_key,
                client=client,
                clock=clock,
                timeout_seconds=gemini.timeout_seconds,
            )
        )
    for endpoint in _openai_compatible_endpoints(settings):
        tuning = config.providers.get(endpoint.name)
        needs_key = endpoint.name != "local"
        if tuning is None or not endpoint.model or (needs_key and endpoint.key is None):
            continue
        providers.append(
            OpenAICompatibleProvider(
                name=endpoint.name,
                model=endpoint.model,
                base_url=endpoint.base_url,
                api_key=endpoint.key,
                external=endpoint.external,
                client=client,
                clock=clock,
                timeout_seconds=tuning.timeout_seconds,
                json_mode=tuning.json_mode,
            )
        )
    return providers


def mock_providers(settings: Settings) -> list[LLMProvider]:
    """Stand-ins for every provider, with the same names and privacy flags as the real ones."""
    return [
        MockProvider(name=endpoint.name, model=f"mock-{endpoint.name}", external=endpoint.external)
        for endpoint in (_gemini_endpoint(settings), *_openai_compatible_endpoints(settings))
    ]


def is_loopback_url(url: str) -> bool:
    """Whether a URL points at this machine."""
    host = urlsplit(url).hostname
    if host is None:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _gemini_endpoint(settings: Settings) -> _Endpoint:
    return _Endpoint(
        "gemini",
        settings.gemini_base_url,
        settings.gemini_api_key,
        settings.gemini_model,
        external=True,
    )


def _openai_compatible_endpoints(settings: Settings) -> list[_Endpoint]:
    return [
        _Endpoint(
            "nvidia",
            settings.nvidia_base_url,
            settings.nvidia_api_key,
            settings.nvidia_model,
            external=True,
        ),
        _Endpoint(
            "hf-large",
            settings.hf_base_url,
            settings.hf_token,
            settings.hf_model_large,
            external=True,
        ),
        _Endpoint(
            "hf-small",
            settings.hf_base_url,
            settings.hf_token,
            settings.hf_model_small,
            external=True,
        ),
        # A "local" server on another host is treated as external, so the consent gate
        # still applies to code that would leave this machine.
        _Endpoint(
            "local",
            settings.local_base_url,
            None,
            settings.local_model,
            external=not is_loopback_url(settings.local_base_url),
        ),
    ]
