"""Liveness endpoint used by the frontend, Docker health checks and CI smoke tests."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Service liveness and the running version."""

    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the service is up."""
    return HealthResponse(status="ok", version=__version__)
