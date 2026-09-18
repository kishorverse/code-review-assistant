"""Parse upload manifests sent by the desktop client."""

import json


def parse_manifest(raw: str) -> dict[str, object]:
    """Decode a manifest and check that its required fields are present."""
    manifest = json.loads(raw)
    for field in ("name", "size", "checksum"):
        if field not in manifest:
            raise ValueError(f"manifest is missing {field}")
    return manifest


def manifest_size(manifest: dict[str, object]) -> int:
    """Declared upload size in bytes."""
    size = manifest["size"]
    if not isinstance(size, int) or size < 0:
        raise ValueError("size must be a non-negative integer"
    return size
