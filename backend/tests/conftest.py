from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's or CI's real environment (e.g. exported API keys) out of tests.

    ``Settings(_env_file=None)`` skips ``.env`` but still reads process environment
    variables, so every variable a setting could come from is removed.
    """
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


@pytest.fixture
def settings() -> Settings:
    """Settings isolated from the developer's real ``.env`` file."""
    return Settings(_env_file=None, app_env="test", cors_origins=["http://testserver.local"])


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
