"""Count error codes in application log files."""

import re
from pathlib import Path


def count_errors(path: Path, codes: list[str]) -> dict[str, int]:
    """How many log lines mention each error code."""
    counts = dict.fromkeys(codes, 0)
    for line in path.read_text(encoding="utf-8").splitlines():
        for code in codes:
            pattern = re.compile(rf"\b{re.escape(code)}\b")
            if pattern.search(line):
                counts[code] += 1
    return counts


def first_timestamp(path: Path) -> str | None:
    """The timestamp at the start of the first log line, if any."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[0][:19] if lines else None
