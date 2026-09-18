"""Write the API's OpenAPI schema, which the frontend generates its types from.

Run from ``backend/`` after changing any endpoint or response model::

    uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    schema = create_app(Settings(_env_file=None, app_env="test")).openapi()
    # LF on every platform, so the file is byte-identical to what CI regenerates.
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.name}: {len(schema['paths'])} paths")


if __name__ == "__main__":
    main()
