"""Provider tuning and task routing, loaded from ``backend/config/providers.yaml``.

Keys and model ids differ per user and live in ``.env``. This file holds what
is the same for everyone: rate limits, concurrency, timeouts and the order in
which each task tries providers, so they can change without code changes.
"""

from pathlib import Path
from typing import Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    model_validator,
)

from app.errors import ConfigError
from app.llm.limits import RateLimits
from app.llm.models import Priority, Task

PROVIDER_NAMES = frozenset({"gemini", "nvidia", "hf-large", "hf-small", "local"})
"""The providers Margin has clients for; ``providers.yaml`` may configure any of them."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LimitsConfig(_Strict):
    """A published budget. Providers that share an account can share one budget."""

    requests_per_minute: PositiveInt | None = None
    tokens_per_minute: PositiveInt | None = None
    requests_per_day: PositiveInt | None = None

    def to_rate_limits(self, safety: float) -> RateLimits:
        """The limiter configuration, with the safety margin applied."""
        return RateLimits(
            requests_per_minute=self.requests_per_minute,
            tokens_per_minute=self.tokens_per_minute,
            requests_per_day=self.requests_per_day,
            safety=safety,
        )


class ProviderTuning(_Strict):
    """How one provider is called."""

    limits: str
    max_concurrency: PositiveInt = 2
    timeout_seconds: PositiveFloat = 60.0
    json_mode: bool = True


class RouterTuning(_Strict):
    """Router-wide behaviour."""

    safety: float = Field(default=0.8, gt=0.0, le=1.0)
    interactive_max_wait_seconds: NonNegativeFloat = 5.0
    batch_max_wait_seconds: NonNegativeFloat = 30.0
    cache_entries: NonNegativeInt = 512

    def max_wait(self, priority: Priority) -> float:
        """How long a request may wait for rate-limit capacity before trying another provider."""
        if priority is Priority.INTERACTIVE:
            return self.interactive_max_wait_seconds
        return self.batch_max_wait_seconds


class ProvidersConfig(_Strict):
    """The whole ``providers.yaml`` file."""

    limits: dict[str, LimitsConfig]
    providers: dict[str, ProviderTuning]
    routing: dict[Task, list[str]]
    router: RouterTuning = RouterTuning()

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        unknown_providers = sorted(set(self.providers) - PROVIDER_NAMES)
        if unknown_providers:
            raise ValueError(
                f"unknown providers: {', '.join(unknown_providers)} "
                f"(expected some of: {', '.join(sorted(PROVIDER_NAMES))})"
            )
        for name, provider in self.providers.items():
            if provider.limits not in self.limits:
                raise ValueError(f"provider {name!r} uses undefined limits {provider.limits!r}")
        missing = [task.value for task in Task if task not in self.routing]
        if missing:
            raise ValueError(f"routing has no entry for: {', '.join(missing)}")
        for task, route in self.routing.items():
            if len(set(route)) != len(route):
                raise ValueError(f"routing for {task.value!r} lists a provider twice")
            unknown = [name for name in route if name not in self.providers]
            if unknown:
                raise ValueError(
                    f"routing for {task.value!r} names unconfigured providers: {', '.join(unknown)}"
                )
        return self


def load_providers_config(path: Path) -> ProvidersConfig:
    """Read and validate the provider configuration file.

    Raises:
        ConfigError: If the file cannot be read, is not YAML or fails validation.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise ConfigError(f"{path} is not UTF-8 text") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    try:
        return ProvidersConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"{path} is invalid: {error}") from error
