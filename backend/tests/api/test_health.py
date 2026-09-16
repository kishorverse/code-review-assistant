from httpx import AsyncClient

from app import __version__


async def test_health_reports_ok_and_version(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_cors_allows_configured_origin(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"Origin": "http://testserver.local"})

    assert response.headers["access-control-allow-origin"] == "http://testserver.local"


async def test_cors_ignores_unknown_origin(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
