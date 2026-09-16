import json
from collections.abc import Iterator

import pytest
import structlog

from app.log import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def test_json_format_emits_one_parseable_object_per_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO", "json")

    structlog.get_logger().info("scan_started", scan_id="abc123")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["event"] == "scan_started"
    assert record["scan_id"] == "abc123"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_events_below_configured_level_are_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "json")

    structlog.get_logger().info("not_shown")
    structlog.get_logger().warning("shown")

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "shown"
