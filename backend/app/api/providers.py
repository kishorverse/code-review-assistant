"""Which LLM providers are enabled and whether each is currently usable."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, NonNegativeFloat

from app.config import LLMMode
from app.llm.breaker import BreakerState
from app.llm.router import Router

router = APIRouter(tags=["providers"])


class ProviderView(BaseModel):
    """One enabled provider. ``external`` providers receive code only with consent."""

    model_config = ConfigDict(frozen=True)

    name: str
    model: str
    external: bool
    state: BreakerState
    reopens_in_seconds: NonNegativeFloat
    reason: str | None


class ProvidersView(BaseModel):
    """The enabled providers and whether models are real or mocked."""

    model_config = ConfigDict(frozen=True)

    mode: LLMMode
    providers: list[ProviderView]


@router.get("/providers")
async def list_providers(request: Request) -> ProvidersView:
    """Enabled providers with their circuit-breaker state, such as paused after a quota error."""
    llm_router: Router = request.app.state.llm_router
    return ProvidersView(
        mode=request.app.state.settings.llm_mode,
        providers=[
            ProviderView(
                name=status.name,
                model=status.model,
                external=status.external,
                state=status.breaker.state,
                reopens_in_seconds=round(status.breaker.reopens_in_seconds, 1),
                reason=status.breaker.reason,
            )
            for status in llm_router.status()
        ],
    )
