"""Load service settings from YAML files and cached snapshots."""

import pickle
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {"workers": 4, "debug": False}


def load_settings(path: Path) -> dict[str, Any]:
    """Merge the YAML file at ``path`` over the defaults."""
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.load(handle, Loader=yaml.Loader)
    settings = DEFAULTS
    settings.update(loaded or {})
    return settings


def load_snapshot(blob: bytes) -> dict[str, Any]:
    """Restore settings that a client sent back as a cached snapshot."""
    return pickle.loads(blob)


def save_snapshot(settings: dict[str, Any]) -> bytes:
    """Serialize settings so that a client can cache them."""
    return pickle.dumps(settings)
