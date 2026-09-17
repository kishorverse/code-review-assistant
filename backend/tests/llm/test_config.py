from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import BACKEND_ROOT
from app.errors import ConfigError
from app.llm.config import load_providers_config
from app.llm.models import Priority, Task

SHIPPED = BACKEND_ROOT / "config" / "providers.yaml"


def valid() -> dict[str, Any]:
    return {
        "limits": {"shared": {"requests_per_minute": 10}, "none": {}},
        "providers": {
            "nvidia": {"limits": "shared", "max_concurrency": 3},
            "local": {"limits": "none", "timeout_seconds": 120},
        },
        "routing": {task.value: ["nvidia", "local"] for task in Task},
    }


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "providers.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_shipped_config_is_valid_and_keeps_the_local_model_as_last_resort() -> None:
    config = load_providers_config(SHIPPED)

    assert set(config.routing) == set(Task)
    assert all(route[-1] == "local" for route in config.routing.values())
    assert config.providers["hf-large"].limits == config.providers["hf-small"].limits


def test_loads_values_and_defaults(tmp_path: Path) -> None:
    config = load_providers_config(write(tmp_path, valid()))

    assert config.limits["shared"].to_rate_limits(0.5).requests_per_minute == 10
    assert config.limits["shared"].to_rate_limits(0.5).safety == 0.5
    assert config.providers["nvidia"].max_concurrency == 3
    assert config.providers["nvidia"].timeout_seconds == 60.0
    assert config.providers["local"].json_mode is True
    assert config.routing[Task.VERIFY] == ["nvidia", "local"]
    assert config.router.max_wait(Priority.INTERACTIVE) == 5.0
    assert config.router.max_wait(Priority.BATCH) == 30.0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data["providers"].update(openai={"limits": "none"}), "unknown providers"),
        (lambda data: data["providers"]["nvidia"].update(limits="missing"), "undefined limits"),
        (lambda data: data["routing"].pop("verify"), "no entry for: verify"),
        (lambda data: data["routing"].update(review=["local", "local"]), "lists a provider twice"),
        (lambda data: data["routing"].update(style=["gemini"]), "unconfigured providers: gemini"),
        (lambda data: data["providers"]["local"].update(timeout=5), "Extra inputs"),
        (lambda data: data["limits"]["shared"].update(requests_per_minute=0), "greater than 0"),
        (lambda data: data.update(router={"safety": 1.5}), "less than or equal to 1"),
    ],
)
def test_rejects_invalid_configuration(tmp_path: Path, change: Any, message: str) -> None:
    data = valid()
    change(data)

    with pytest.raises(ConfigError, match=message):
        load_providers_config(write(tmp_path, data))


def test_rejects_unreadable_and_malformed_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("limits: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="cannot read"):
        load_providers_config(tmp_path / "missing.yaml")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_providers_config(broken)
    with pytest.raises(ConfigError, match="is invalid"):
        load_providers_config(write(tmp_path, ["not", "a", "mapping"]))
