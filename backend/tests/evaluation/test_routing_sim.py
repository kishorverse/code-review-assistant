import pytest

from app.errors import ProviderUnavailableError, RateLimitedError
from evaluation.routing_sim import (
    ScaledClock,
    Scenario,
    ServerSpec,
    SimulatedServer,
    run_plain,
    run_router,
)

SMALL = Scenario(
    name="small",
    description="12 calls against a 6 RPM provider with a fallback",
    requests=12,
    servers=(ServerSpec("primary", 6, 1.0), ServerSpec("fallback", 30, 1.0)),
)


async def test_the_simulated_server_enforces_its_limit_and_outages() -> None:
    clock = ScaledClock(scale=600)
    server = SimulatedServer("s", requests_per_minute=2, latency_seconds=0, clock=clock)
    await server.handle()
    await server.handle()

    with pytest.raises(RateLimitedError) as limited:
        await server.handle()
    server.down = True
    with pytest.raises(ProviderUnavailableError):
        await server.handle()

    assert limited.value.retry_after is not None
    assert 0 < limited.value.retry_after <= 60
    assert (server.served, server.rejected, server.failed) == (2, 1, 1)


async def test_the_router_completes_a_burst_without_429s() -> None:
    naive = await run_plain(SMALL, honour_retry_after=False)
    routed = await run_router(SMALL)

    assert naive.rejected_429 > 0
    assert routed.completed == SMALL.requests
    assert routed.rejected_429 == 0


async def test_the_router_survives_an_outage_of_the_preferred_provider() -> None:
    outage = Scenario(
        name="outage",
        description="preferred provider down",
        requests=8,
        servers=(ServerSpec("primary", 6, 1.0, down=True), ServerSpec("fallback", 30, 1.0)),
    )

    naive = await run_plain(outage, honour_retry_after=True)
    routed = await run_router(outage)

    assert naive.completed == 0
    assert (routed.completed, routed.served_by_fallback) == (8, 8)
